# Deployment Guide

This project is designed to run continuously on an Ubuntu 24.04 VPS.

## VPS Initial Setup
1. SSH into your VPS.
2. Install Docker and Docker Compose plugin.
3. Clone the repository: `git clone <your-repo-url> ~/llm-trading-agent`
4. Setup `.env`: `cp .env.example .env` and edit your secrets securely.

## CI/CD Pipeline
GitHub Actions are configured to automatically deploy changes pushed to `main`.
You must add the following GitHub Secrets to your repository:
- `VPS_HOST` (IP address)
- `VPS_USER` (e.g. root or ubuntu)
- `VPS_PORT` (usually 22)
- `VPS_SSH_KEY` (Your private key corresponding to the public key on the VPS)

When code is merged to main, GitHub will SSH into the server, update the repository, and seamlessly restart the Docker containers. Your `.env` will persist safely on the host machine.
