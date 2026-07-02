.PHONY: demo-up demo-down demo-reset soar-restart bridge-restart llm-restart

demo-up:
	cd lab && vagrant up
	@echo "Lab up. Waiting 10s for services..."
	@sleep 10

demo-down:
	cd lab && vagrant halt

demo-reset:
	redis-cli -h 192.168.56.10 --scan --pattern 'incident:*' | xargs -r redis-cli -h 192.168.56.10 DEL
	vagrant ssh lab-manager -c "sudo systemctl restart argos-bridge"
	@echo "Demo state reset."

soar-restart:
	pkill -f 'soar.decision_engine.consumer' || true
	pkill -f 'uvicorn soar.approval_api' || true
	sleep 1
	nohup python -m soar.decision_engine.consumer > /tmp/soar-consumer.log 2>&1 &
	nohup uvicorn soar.approval_api.main:app --port 8001 > /tmp/soar-api.log 2>&1 &

bridge-restart:
	vagrant ssh lab-manager -c "sudo systemctl restart argos-bridge"

llm-restart:
	pkill -f 'ml.consumer' || true
	sleep 1
	nohup python -m ml.consumer > /tmp/ml.log 2>&1 &