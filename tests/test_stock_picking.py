# This file is part of the stock_picking module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase


class StockPickingTestCase(ModuleTestCase):
    'Test Stock Picking module'
    module = 'stock_picking'


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        StockPickingTestCase))
    return suite