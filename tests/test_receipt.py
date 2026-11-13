"""Run from project root: python -m unittest discover -s tests -v"""
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

class ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dbfile = Path(cls.tmp.name) / 'receipt.db'
        os.environ['DATABASE_URL'] = f'sqlite:///{cls.dbfile}'
        os.environ['SECRET_KEY'] = 'test-only-secret-not-for-production'
        from app import app, db, Food, ReceiptImport
        cls.app, cls.db, cls.Food, cls.ReceiptImport = app, db, Food, ReceiptImport
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.engine.dispose()
        cls.tmp.cleanup()

    def setUp(self):
        with self.app.app_context():
            self.db.session.query(self.Food).delete()
            self.db.session.query(self.ReceiptImport).delete()
            self.db.session.commit()

    def csrf(self):
        self.client.get('/receipt')
        with self.client.session_transaction() as sess:
            return sess['receipt_csrf']

    def start(self, value):
        return self.client.post('/receipt/analyze', data={'csrf': self.csrf(), 'manual': value})

    def confirm(self, review, changes=None):
        html = review.data.decode()
        token = re.search(r'name="token" value="([^"]+)"', html).group(1)
        data = {'token': token, 'csrf': self.csrf(), 'include_0': 'on',
                'name_0':'牛乳','quantity_0':'2','unit_0':'本','category_0':'乳製品','expiration_0':''}
        if changes:
            data.update(changes)
        return self.client.post('/receipt/confirm', data=data)

    def test_bulk_register_and_prevent_replay(self):
        review = self.start('牛乳,2,本,乳製品')
        self.assertEqual(review.status_code, 200)
        self.assertEqual(self.confirm(review).status_code, 302)
        self.assertEqual(self.confirm(review).status_code, 409)
        with self.app.app_context():
            self.assertEqual(self.Food.query.filter_by(name='牛乳').one().quantity, 2)

    def test_merge_matching_existing_food(self):
        with self.app.app_context():
            self.db.session.add(self.Food(name='牛乳', quantity=2, unit='本', category='乳製品'))
            self.db.session.commit()
        review = self.start('牛乳,1,本,乳製品')
        self.assertEqual(self.confirm(review, {'quantity_0':'1'}).status_code, 302)
        with self.app.app_context():
            self.assertEqual(self.Food.query.filter_by(name='牛乳').count(), 1)
            self.assertEqual(self.Food.query.filter_by(name='牛乳').one().quantity, 3)

    def test_bad_quantity_does_not_write(self):
        review = self.start('牛乳,1,本,乳製品')
        self.assertEqual(self.confirm(review, {'quantity_0':'10001'}).status_code, 400)
        with self.app.app_context():
            self.assertEqual(self.Food.query.filter_by(name='牛乳').count(), 0)

    def test_no_csrf(self):
        self.assertEqual(self.client.post('/receipt/analyze', data={'manual':'牛乳'}).status_code, 403)

    def test_bad_file(self):
        from io import BytesIO
        response = self.client.post('/receipt/analyze', data={
            'csrf':self.csrf(), 'receipt':(BytesIO(b'not an image'), 'receipt.jpg')},
            content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)

if __name__ == '__main__':
    unittest.main()
