from app import create_app, db
from app.services.market_prices import fetch_and_store_prices
import traceback
app = create_app()
app.app_context().push()
try:
    print('Fetching prices...')
    fetch_and_store_prices(app)
    print('Done!')
except Exception as e:
    with open("err.txt", "w") as f:
        traceback.print_exc(file=f)
