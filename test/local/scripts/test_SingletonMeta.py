import unittest

from common import BrokerNodeConnection, ConfluenceConnection, ConfluenceNodeMapper, PropertiesReader


class TestSingletonMeta(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        PropertiesReader().load_properties_as_env_vars('settings.json')

    def test_BrokerNodeConnection(self):
        connection1 = BrokerNodeConnection()
        connection2 = BrokerNodeConnection()
        self.assertEqual(id(connection1), id(connection2))

    def test_ConfluenceConnection(self):
        connection1 = ConfluenceConnection()
        connection2 = ConfluenceConnection()
        self.assertEqual(id(connection1), id(connection2))

    def test_ConfluenceNodeMapper(self):
        mapper1 = ConfluenceNodeMapper()
        mapper2 = ConfluenceNodeMapper()
        self.assertEqual(id(mapper1), id(mapper2))


if __name__ == '__main__':
    unittest.main()
