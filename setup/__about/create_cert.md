# Certificate Generator

**Script:** [Certificate Generator (script)](../create_cert.py)

## Purpose

One-time generator for the self-signed code-signing certificate that
`build.py`'s `sign_file()` needs. Creates `setup/cert/{APP_NAME}.pfx` — a
5-year `CodeSigningCert`, `CN=UVuruna` — via PowerShell's
`New-SelfSignedCertificate` + `Export-PfxCertificate`, protected with the
password already sitting in `setup/cert/password.txt`. Run once, then reused
across every future build; re-run only if the certificate expires or is
lost.

## Connections

### Uses
- none — reads only `setup/app_info.json` (for the `.pfx` filename) and
  `setup/cert/password.txt`, neither of which is a project module

### Used by
- none (run directly and once via `python setup/create_cert.py`; `build.py`
  reads its OUTPUT — the `.pfx` and `password.txt` files — but never
  imports or calls this script)

## Functions

- `_load_password() -> str` — reads `setup/cert/password.txt`; raises
  `FileNotFoundError` with setup instructions if it is missing. Unlike
  `build.py`'s lazy `sign_file()`, this script reads the password
  EAGERLY at module import time (`PFX_PASSWORD = _load_password()`) —
  the password must already be decided before a certificate can be minted
  with it, so there is no useful "run partially without it" path here.
- `create_certificate()` — the only real function. If `setup/cert/{name}.pfx`
  already exists, prints a message and returns without touching it (no
  silent overwrite). Otherwise creates `setup/cert/`, builds the PowerShell
  script above, runs it via `subprocess.run(["powershell", ...])`, exits `1`
  on a non-zero return code, and on success prints the certificate
  thumbprint plus a reminder that `setup/cert/` is gitignored and must never
  be committed.
