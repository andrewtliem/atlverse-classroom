import os
import unittest
from unittest.mock import patch

from app import app, db, inject_daily_quote

class QuoteContextProcessorTest(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    @patch('app.AIService')
    def test_inject_daily_quote_returns_quote(self, mock_service):
        mock_service.return_value.get_daily_quote.return_value = 'CS fact'
        with app.app_context():
            context = inject_daily_quote()
            self.assertIn('daily_quote', context)
            self.assertTrue(context['daily_quote'])

if __name__ == '__main__':
    unittest.main()
