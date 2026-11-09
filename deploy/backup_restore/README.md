# Site-scoped maintenance fallback

This repository does not contain the active Docker proxy configuration or its
site volume mounts. Deploy `maintenance.html` on the reverse proxy host and add
the following **inside the server block for the target site only**, adapting
the alias to the mounted file. Do not place it in a shared/default server block.

```nginx
proxy_intercept_errors on;
error_page 502 503 504 =503 /almadina-maintenance.html;
location = /almadina-maintenance.html {
    internal;
    alias /absolute/proxy/path/to/maintenance.html;
    add_header Cache-Control "no-store" always;
    add_header Retry-After "30" always;
}
```

Verify with `nginx -t`, then reload only that proxy. Simulate an upstream 503
on a disposable site and confirm that the page is served with HTTP 503. This
fallback cannot show live phases: the backup panel resumes status polling when
Frappe is reachable again. If recovery is uncertain, maintenance remains on
and an administrator must investigate the protected per-site restore state and
runner log before reopening the site.
