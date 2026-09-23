.PHONY: install test lint eval run-web run-cli docker-build

install:
	pip install -e ".[dev,gcp]"

test:
	PYTHONPATH=. python3 -m unittest discover -s tests/unit -p "test_*.py" -v

lint:
	ruff check pressbox_war_room tests

eval:
	adk eval pressbox_war_room tests/eval/scouting_eval.evalset.json --config_file_path=tests/eval/test_config.json --print_detailed_results

run-web:
	adk web .

run-cli:
	adk run pressbox_war_room

docker-build:
	docker build -t pressbox-war-room:latest .
