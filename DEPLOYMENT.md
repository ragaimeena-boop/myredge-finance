# Unraid & Cloudflared Deployment Guide

Step-by-step guidance for running the **Personal Finance Dashboard** on your Unraid server with **Cloudflared Tunnel** access.

---

## 1. Files & Folders to Transfer to Unraid

Copy the following files and folders from this project folder (`Financial Advisor`) into `/mnt/user/appdata/finance-dashboard/` on your Unraid server:

```text
/mnt/user/appdata/finance-dashboard/
├── app/                  <-- Entire folder (Python code, templates, static CSS)
├── tests/                <-- Entire folder (Sample fixtures)
├── Dockerfile            <-- Container build definition
├── docker-compose.yml    <-- Container configuration
├── requirements.txt      <-- Python dependencies
└── .env                  <-- Environment secrets file
```

---

### How to Transfer the Files to Unraid (Choose 1 Method):

#### Method A: Using Unraid Network Share (SMB) - Easiest
1. On your PC, open File Explorer and connect to your Unraid SMB share:
   `\\YOUR-UNRAID-IP\appdata\` (e.g. `\\192.168.1.100\appdata\`)
2. Create a folder named `finance-dashboard`.
3. Copy all files listed above (`app/`, `tests/`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`) into `\\YOUR-UNRAID-IP\appdata\finance-dashboard\`.

#### Method B: Using WinSCP / FileZilla (SFTP/SSH)
1. Connect via WinSCP to your Unraid IP using user `root` and your Unraid root password.
2. Navigate to `/mnt/user/appdata/`.
3. Create folder `finance-dashboard` and drag/drop the project files.

---

## 2. Environment Configuration (`.env`)

Create a `.env` file in `/mnt/user/appdata/finance-dashboard/`:

```env
# SIMPLEFIN ACCESS URL (Optional for initial setup; leave blank to use fixture data)
SIMPLEFIN_ACCESS_URL=https://username:password@bridge.simplefin.org/simplefin/claim/xxx

# Database Path (Stored in persistent /app/data container volume)
DATABASE_URL=sqlite:///./data/finance.db

# Timezone
TIMEZONE=America/New_York

# Custom Port for Cloudflared Tunnel
PORT=8585
```

---

## 3. Running on Unraid (Docker Compose or Docker CLI)

### Option A: Using `docker-compose` (Recommended for Unraid Terminal)
Run the following inside `/mnt/user/appdata/finance-dashboard`:
```bash
docker-compose up -d --build
```
*(Note: Unraid uses the hyphenated `docker-compose` command).*

### Option B: Building via Docker CLI (Without Docker Compose)
If your Unraid does not have `docker-compose` installed:
```bash
cd /mnt/user/appdata/finance-dashboard
docker build -t myredge-finance:latest .
docker run -d \
  --name finance-dashboard \
  --restart unless-stopped \
  -p 8588:8585 \
  -v /mnt/user/appdata/finance-dashboard/data:/app/data \
  myredge-finance:latest
```

---

## 4. Cloudflared Tunnel Configuration

To expose the dashboard securely through your existing Cloudflared tunnel:

1. Open your **Cloudflare Zero Trust Dashboard** -> **Networks** -> **Tunnels**.
2. Edit your active tunnel and click **Public Hostname**.
3. Add a new Public Hostname:
   - **Subdomain**: `finance` (or `money`)
   - **Domain**: `yourdomain.com`
   - **Service Type**: `HTTP`
   - **URL**: `http://<UNRAID-LOCAL-IP>:8588` (e.g. `http://192.168.1.100:8588`)
4. Save the hostname.

You can now navigate to `https://finance.yourdomain.com` from anywhere in the world!

---

## 5. Adding your SimpleFIN Access URL later

When you get your SimpleFIN Access URL:
1. Edit your `.env` file and set:
   ```env
   SIMPLEFIN_ACCESS_URL=https://<user>:<pass>@bridge.simplefin.org/simplefin/accounts
   ```
2. Restart the container:
   ```bash
   docker compose restart
   ```
3. The dashboard will automatically pull live data at 6:00 AM Eastern daily, or whenever you click **⚡ Sync Now** on the dashboard home page.
