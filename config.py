import os
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv('ODOO_URL', 'http://localhost:8069')
ODOO_DB = os.getenv('ODOO_DB', 'odoo')
SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
