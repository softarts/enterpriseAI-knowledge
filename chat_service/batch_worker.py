"""Independent, queue-free batch import worker process."""

import argparse
import logging

from chat_service.services.batch_import_service import BatchImportWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Process one persisted batch import task")
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    BatchImportWorker().run(args.task_id)


if __name__ == "__main__":
    main()
