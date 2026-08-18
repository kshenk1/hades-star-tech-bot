# Deploying hadesbot on EC2 (Amazon Linux 2023, t3.micro)

## 1. Launch the instance

- AMI: **Amazon Linux 2023** (not AL2 — this script uses `dnf`, AL2's default
  Python is too old anyway)
- Instance type: `t3.micro` is plenty — this bot is I/O-bound, barely touches CPU
- Storage: default 8GB gp3 is fine
- Security group: **no inbound rules needed at all**. The bot only makes
  outbound connections to Discord's gateway/API — you don't need to open any ports.
- Key pair: Use SSM instead

## 2. Get the code onto the box

From your machine:
```bash
aws ssm start-session --target the-hades-bot-instance --region us-east-1
```
or clone from git directly on the box if you've pushed it to a repo:
```bash
git clone <your-repo-url> hades-star-tech-bot
cd hades-star-tech-bot/hadesbot
```

## 3. Run setup (once)

```bash
cd hadesbot   # wherever you copied/cloned it
sudo bash deploy/setup.sh
```

This installs Python 3.11, creates an unprivileged `hadesbot` system user,
copies the project to `/opt/hadesbot`, builds a venv, installs the systemd
unit, and enables it (so it starts automatically on instance reboot).

## 4. Add your token and start it

```bash
sudo nano /opt/hadesbot/.env
```
Fill in your real `DISCORD_TOKEN` (same value as your local `.env`). Save, then:
```bash
sudo systemctl start hadesbot
sudo journalctl -u hadesbot -f
```
You should see the same "Seeded X mod types..." / "Logged in as..." / "Synced
N commands" lines you saw running it locally. Ctrl+C exits the log tail
without stopping the service.

## Operating it day-to-day

```bash
sudo systemctl status hadesbot     # is it running?
sudo systemctl stop hadesbot
sudo systemctl start hadesbot
sudo systemctl restart hadesbot
sudo journalctl -u hadesbot -f     # follow logs live
sudo journalctl -u hadesbot -n 200 # last 200 log lines
```

It's `enable`d, so it comes back automatically after an instance reboot —
you don't need to SSH in and start it by hand after a reboot.

## Deploying code changes later

After editing code locally and pushing/copying the update to the box:
```bash
sudo bash deploy/redeploy.sh
```
This re-syncs the code (leaving `.env`, the venv, and `hadesbot.db` alone),
reinstalls requirements in case `requirements.txt` changed, and restarts
the service.

## About the SQLite file

`hadesbot.db` lives at `/opt/hadesbot/hadesbot.db`, owned by the `hadesbot`
user. It's on the instance's own EBS volume, so it survives reboots and
`redeploy.sh` runs (both scripts explicitly exclude it from the sync).

It does **not** survive instance *termination* — if you ever terminate this
EC2 instance rather than just stopping it, the volume goes with it unless you
detach/snapshot it first. For a single-team internal tool this is usually
fine, but worth knowing. A quick manual backup any time:
```bash
sudo cp /opt/hadesbot/hadesbot.db ~/hadesbot-backup-$(date +%F).db
scp -i your-key.pem ec2-user@<instance-ip>:~/hadesbot-backup-*.db .
```

## Why a t3.micro is plenty

This bot holds a single websocket connection to Discord's gateway and does
occasional SQLite reads/writes on slash commands from one team. It'll sit at
low single-digit percent CPU and a few dozen MB of RAM. If you're on the AWS
Free Tier, a single t3.micro running 24/7 falls within the free-tier hours
allotment... for now.
