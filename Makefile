.PHONY: clients deploy

GOLF_HOST := simon@golf
GOLF_DIR := ~/golfcart

clients:
	chmod +x scripts/generate_clients.sh && scripts/generate_clients.sh

# Deploys packages/api to the "golf" Raspberry Pi (runs the API next to the
# golf cart's BMS over Tailscale). Pushes the current branch, then pulls,
# syncs deps, migrates, and restarts the systemd service on golf.
deploy:
	git push
	ssh $(GOLF_HOST) 'cd $(GOLF_DIR) && git pull && cd packages/api && ~/.local/bin/uv sync && ~/.local/bin/uv run task db_migrate && sudo systemctl restart bessel-api && sleep 2 && systemctl is-active bessel-api'
