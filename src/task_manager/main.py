from presentation.app import create_app
from logging_config import configure_logging

configure_logging()
app = create_app()
