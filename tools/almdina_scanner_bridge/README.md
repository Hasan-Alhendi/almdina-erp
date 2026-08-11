# Almdina Scanner Bridge

A small Windows-only local bridge used by the Almdina ERP special-door editor to acquire the paper sketch directly from a scanner/printer.

## Why it exists

A normal browser page cannot call the Windows WIA scanner API directly. The ERP UI therefore talks only to a loopback service on `127.0.0.1`; that service opens the standard Windows scanner UI and returns the acquired image to the browser. The image is then uploaded to Frappe as a **private File** and only the file URL is stored in the special-door drawing JSON.

## Run manually for testing

1. Connect/install the printer-scanner in Windows and verify that Windows can scan from it.
2. Open PowerShell.
3. Run `AlmdinaScannerBridge.ps1`.
4. If Windows reports an URL ACL error, open PowerShell once as Administrator and run:

```powershell
netsh http add urlacl url=http://127.0.0.1:17831/ user=$env:USERNAME
```

Then run the bridge normally again.

The default allowed ERP origin is `https://almadina-2.horizontechco.com`. Additional development origins can be passed with `-AllowedOrigins`.

## Endpoints

- `GET /health` — bridge readiness check.
- `POST /scan` — opens the standard Windows scanner UI and returns one JPEG image. Cancelling the Windows dialog returns HTTP 204.

The bridge listens on loopback only and validates the browser `Origin` before allowing scan requests.
