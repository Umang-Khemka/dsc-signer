# dsc-signer

Bulk-signs PDF reports from a Google Drive folder shared with you, using the DSC on your USB token.
Signed copies go to a **new folder in your own Drive** (`Signed Reports`, mirroring the folder structure)
and to `SIGNED_DIR` on your disk. Originals are never touched.

```
Drive (shared folder) -> enqueue -> BullMQ/Redis (concurrency 1) -> worker
    worker: download -> Python signer (token) -> upload signed copy
```

## One-time setup (Windows)

1. **Python packages**: `pip install -r signer/requirements.txt`
2. **Node packages**: `npm install`
3. **Redis**: `docker compose up -d` (or use WSL / Memurai if you don't have Docker)
4. **Google OAuth** (Cloud Console):
   - Create a project, enable the **Google Drive API**.
   - OAuth consent screen -> External -> add your own Google account as a **test user**.
   - Credentials -> Create **OAuth client ID** -> *Desktop app* -> download as `credentials.json` into this folder.
   - The first run opens a browser to sign in. Use the Google account that has the shared folder.
5. **Config**: copy `.env.example` to `.env` and fill in:
   - `SOURCE_FOLDER_ID`: the ID at the end of the BLR folder URL (`drive.google.com/drive/folders/<ID>`).
   - `CERT_LABEL`: run `python signer/sign_worker.py --list`, enter the PIN, copy the certificate's label.

## Run

```powershell
npm run typecheck          # optional sanity check
npm run enqueue            # lists all PDFs, queues them, writes D:\dsc-work\manifest.json
npm run worker             # asks for the token PIN once, then signs everything
npm run status             # counts: waiting / active / completed / failed
npm run status -- --failed # which files failed and why
npm run status -- --retry  # put failed files back in the queue
```

**Do a small trial first.** Before the full run, enqueue, let the worker finish 3-5 files, open the signed
copies in Adobe Reader, and check the signature is valid and the stamp doesn't overlap anything.
Then let it run on the rest. Stop any time with Ctrl+C; running `npm run worker` again resumes
(files already uploaded are skipped).

## Notes

- The PIN is typed into the terminal and passed to the Python process over stdin. It is never saved.
  After 3 failures in a row the worker stops, to avoid hammering a token that was unplugged.
- Stamp position is `BOX_FRAC` at the top of `signer/sign_worker.py` (fractions of the last page).
- Optional: set `TSA_URL` to embed a trusted timestamp; `CA_CHAIN_FILES` to embed CA certificates.
- If a download fails with a 403, the owner has disabled downloading for viewers. Ask them to allow it.
- OAuth apps in "Testing" mode expire the login after 7 days. Delete `token.json` and sign in again if so.
