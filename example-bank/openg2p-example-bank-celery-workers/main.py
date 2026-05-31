from openg2p_example_bank_celery_workers.app import Initializer, celery_app
from openg2p_fastapi_common.ping import PingInitializer

initializer = Initializer()
PingInitializer()

app = initializer.return_app()
celery_app = celery_app

if __name__ == "__main__":
    initializer.main()
