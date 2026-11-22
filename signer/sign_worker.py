"""
Long-running PDF signer. Node sends one JSON line per file on stdin, this replies
with one JSON line on stdout. Logs go to stderr only (stdout is the protocol).

Startup protocol:
  1. first stdin line = token PIN (never written to disk, never on the command line)
  2. replies {"event":"ready","signer":"<CN>"} or {"event":"error","error":"..."}
Then per request: {"id":1,"src":"in.pdf","dst":"out.pdf"}
  -> {"id":1,"ok":true} or {"id":1,"ok":false,"error":"..."}

  python sign_worker.py --list                 # objects on the token (find KEY_ID)
  python sign_worker.py --sign in.pdf out.pdf  # sign one PDF to test the token
"""
import getpass
import json
import logging
import os
import sys
import traceback

from pypdf import PdfReader
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.text import TextBox, TextBoxStyle
from pyhanko.pdf_utils.font.basic import SimpleFontEngineFactory
from pyhanko.pdf_utils.layout import (
    AxisAlignment,
    InnerScaling,
    Margins,
    SimpleBoxLayoutRule,
)
from pyhanko.sign import fields, signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.stamp import TextStampStyle


def _load_env_file():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env_file()

LIB = os.environ.get("PKCS11_LIB", r"C:\Windows\System32\HYP2003csp11IND.dll")
CERT_LABEL = os.environ.get("CERT_LABEL", "")
KEY_LABEL = os.environ.get("KEY_LABEL", "") or CERT_LABEL
# Preferred for tokens whose labels are odd (e.g. 'eMudhra\x00'): exported certificate file + key ID (hex)
CERT_FILE = os.environ.get("CERT_FILE", "")
KEY_ID = os.environ.get("KEY_ID", "").replace(" ", "")
CA_CHAIN_FILES = [p for p in os.environ.get("CA_CHAIN_FILES", "").split(";") if p]
TSA_URL = os.environ.get("TSA_URL", "")

# Stamp box as fractions of the LAST page (bottom-right, above the footer).
# (x1, y1, x2, y2) measured from bottom-left.
BOX_FRAC = (0.42, 0.08, 0.94, 0.18)
FIELD_NAME = "Sig1"
STAMP_TEXT = (
    "Digitally signed by\n"
    "%(signer)s\n"
    "Date: %(ts)s"
)


# We only check file integrity here; trust is decided by the viewer (Adobe), so silence trust-path noise
for _name in ("pyhanko", "pyhanko_certvalidator"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def stamp_box(src_path):
    page = PdfReader(src_path).pages[-1]
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    x1, y1, x2, y2 = BOX_FRAC
    return (w * x1, h * y1, w * x2, h * y2)


def sign_pdf(signer, src, dst, timestamper=None):
    """Sign src -> dst with a visible stamp on the last page, then check integrity."""
    font = SimpleFontEngineFactory("Helvetica", 0.5)
    tmp = dst + ".part"
    with open(src, "rb") as f:
        # strict=False: allow PDFs with hybrid cross-reference tables
        w = IncrementalPdfFileWriter(f, strict=False)
        fields.append_signature_field(
            w, fields.SigFieldSpec(FIELD_NAME, on_page=-1, box=stamp_box(src))
        )

        # Left column: big signer name. Right column: "Digitally signed by ..." details.
        name = signer.signing_cert.subject.native["common_name"]
        big_name = TextBox(TextBoxStyle(font=font, font_size=14), w, font_name="F2")
        big_name.content = "\n".join(name.split())
        pad = Margins(left=6, right=6, top=4, bottom=4)
        style = TextStampStyle(
            stamp_text=STAMP_TEXT,
            border_width=0,
            text_box_style=TextBoxStyle(font=font, font_size=8),
            background=big_name,
            background_opacity=1.0,
            background_layout=SimpleBoxLayoutRule(
                x_align=AxisAlignment.ALIGN_MIN,
                y_align=AxisAlignment.ALIGN_MID,
                margins=pad,
                inner_content_scaling=InnerScaling.NO_SCALING,
            ),
            inner_content_layout=SimpleBoxLayoutRule(
                x_align=AxisAlignment.ALIGN_MAX,
                y_align=AxisAlignment.ALIGN_MID,
                margins=pad,
                inner_content_scaling=InnerScaling.NO_SCALING,
            ),
        )

        meta = signers.PdfSignatureMetadata(field_name=FIELD_NAME, md_algorithm="sha256")
        ps = signers.PdfSigner(
            meta, signer=signer, stamp_style=style, timestamper=timestamper
        )
        with open(tmp, "wb") as out:
            ps.sign_pdf(w, output=out)

    # Integrity check only (trust is the viewer's job): file intact, signature math OK
    with open(tmp, "rb") as f:
        sigs = PdfFileReader(f, strict=False).embedded_signatures
        if not sigs:
            raise RuntimeError("no signature found after signing")
        st = validate_pdf_signature(sigs[-1])
        if not (st.intact and st.valid):
            raise RuntimeError(f"signature failed integrity check: {st.summary()}")
    os.replace(tmp, dst)


def open_session(pin):
    from pyhanko.sign.pkcs11 import open_pkcs11_session

    return open_pkcs11_session(LIB, user_pin=pin)


def build_pkcs11_signer(session):
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.sign.pkcs11 import PKCS11Signer

    kwargs = {}
    if CERT_FILE:
        kwargs["signing_cert"] = load_cert_from_pemder(CERT_FILE)
    elif CERT_LABEL:
        kwargs["cert_label"] = CERT_LABEL
    elif KEY_ID:
        pass  # certificate is read from the token using the same ID as the key
    else:
        raise RuntimeError("Set KEY_ID (from --list), or CERT_FILE / CERT_LABEL, in .env")

    if KEY_ID:
        kwargs["key_id"] = bytes.fromhex(KEY_ID)
    elif KEY_LABEL:
        kwargs["key_label"] = KEY_LABEL
    else:
        raise RuntimeError("Set KEY_ID (from --list) or KEY_LABEL in .env")

    if CA_CHAIN_FILES:
        kwargs["ca_chain"] = [load_cert_from_pemder(p) for p in CA_CHAIN_FILES]
    return PKCS11Signer(session, **kwargs)


def build_timestamper():
    if not TSA_URL:
        return None
    from pyhanko.sign import timestamps

    return timestamps.HTTPTimeStamper(TSA_URL)


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def serve():
    pin = sys.stdin.readline().rstrip("\r\n")
    try:
        session = open_session(pin)
        signer = build_pkcs11_signer(session)
        tsa = build_timestamper()
        signer.signing_cert  # loads the certificate from the token (fails fast on bad label)
        send({"event": "ready", "signer": signer.signing_cert.subject.human_friendly})
    except Exception as e:  # wrong PIN, no token, bad label...
        send({"event": "error", "error": f"{type(e).__name__}: {e}"})
        return 1

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        try:
            sign_pdf(signer, req["src"], req["dst"], tsa)
            send({"id": req["id"], "ok": True})
        except Exception as e:
            log(traceback.format_exc())
            send({"id": req["id"], "ok": False, "error": f"{type(e).__name__}: {e}"})
    return 0


def list_objects():
    import pkcs11
    from pkcs11 import Attribute, ObjectClass

    def attr(o, a):
        try:
            return o[a]
        except Exception:
            return None

    pin = getpass.getpass("Token PIN: ")
    token = pkcs11.lib(LIB).get_token()
    with token.open(user_pin=pin) as s:
        for o in s.get_objects():
            cls = attr(o, Attribute.CLASS)
            try:
                cls = ObjectClass(cls).name
            except Exception:
                cls = str(cls)
            oid = attr(o, Attribute.ID)
            oid = bytes(oid).hex() if oid is not None else "?"
            print(f"{cls:12} label={attr(o, Attribute.LABEL)!r:18} id={oid}")


def sign_one(src, dst):
    """Sign a single PDF using the token (no Drive, no queue). For testing."""
    pin = getpass.getpass("Token PIN: ")
    session = open_session(pin)
    signer = build_pkcs11_signer(session)
    print("Signing as:", signer.signing_cert.subject.human_friendly)
    sign_pdf(signer, src, dst, build_timestamper())
    print("Done ->", dst)


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_objects()
    elif "--sign" in sys.argv:
        i = sys.argv.index("--sign")
        sign_one(sys.argv[i + 1], sys.argv[i + 2])
    else:
        sys.exit(serve())