# Networking

The default browser address is `http://localhost:8081`. Other LAN devices can use `http://<verified-server-LAN-address>:8081` after the host firewall allows the port on the private network. The app intentionally does not guess a LAN address.

Tailscale integration is not active in this build. Install and authorize Tailscale on the host and intended devices using its official process; the app does not receive host networking privileges, access the Docker socket, or claim a connection based on a preference selection.

For remote public access, use a domain with TLS through Caddy or a Cloudflare Tunnel. Keep the database and backend private. Direct port forwarding is an advanced choice and should expose only the TLS reverse proxy.
