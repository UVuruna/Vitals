"""
Create a self-signed code signing certificate for the app.

Run once to generate the certificate. The .pfx file is used by
build.py to sign the exe. Keep the .pfx file private — do NOT
commit it to git.

Usage:
    python setup/create_cert.py
"""

import json
import subprocess
import sys
from pathlib import Path

SETUP_DIR = Path(__file__).parent
CERT_DIR = SETUP_DIR / "cert"
APP_INFO_PATH = SETUP_DIR / "app_info.json"
APP_NAME = json.loads(APP_INFO_PATH.read_text(encoding="utf-8"))["name"]
PFX_PATH = CERT_DIR / f"{APP_NAME}.pfx"
PASSWORD_PATH = CERT_DIR / "password.txt"
PUBLISHER = "UVuruna"


def _load_password() -> str:
    if not PASSWORD_PATH.exists():
        raise FileNotFoundError(
            f"Password file not found: {PASSWORD_PATH}\n"
            "Create setup/cert/password.txt with the certificate password."
        )
    return PASSWORD_PATH.read_text(encoding="utf-8").strip()


PFX_PASSWORD = _load_password()


def create_certificate():
    if PFX_PATH.exists():
        print(f"Certificate already exists: {PFX_PATH}")
        print("Delete it manually if you want to regenerate.")
        return

    CERT_DIR.mkdir(exist_ok=True)

    # PowerShell script to create self-signed code signing cert
    # and export it as .pfx
    ps_script = f"""
    $cert = New-SelfSignedCertificate `
        -Subject "CN={PUBLISHER}" `
        -Type CodeSigningCert `
        -CertStoreLocation Cert:\\CurrentUser\\My `
        -NotAfter (Get-Date).AddYears(5)

    $pwd = ConvertTo-SecureString -String "{PFX_PASSWORD}" -Force -AsPlainText

    Export-PfxCertificate `
        -Cert $cert `
        -FilePath "{PFX_PATH.as_posix()}" `
        -Password $pwd

    Write-Host "Certificate thumbprint: $($cert.Thumbprint)"
    Write-Host "Exported to: {PFX_PATH.as_posix()}"
    """

    print(f"Creating self-signed certificate for '{PUBLISHER}'...")
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)

    print(result.stdout)
    print(f"Certificate created: {PFX_PATH}")
    print(f"Password: {PFX_PASSWORD}")
    print()
    print("IMPORTANT: setup/cert/ is gitignored — never commit certificates!")


if __name__ == "__main__":
    create_certificate()
