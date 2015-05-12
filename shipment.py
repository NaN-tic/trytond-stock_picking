#This file is part stock_picking module for Tryton.
#The COPYRIGHT file at the top level of this repository contains 
#the full copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool, PoolMeta

__all__ = ['ShipmentOut', 'ShipmentOutPicking', 'ShipmentOutPickingLine',
    'ShipmentOutPickingResult', 'ShipmentOutPacked']
__metaclass__ = PoolMeta


class ShipmentOut:
    __name__ = 'stock.shipment.out'

    @classmethod
    def picking_before(cls, shipment):
        return

    @classmethod
    def picking_after(cls, shipment):
        return


class ShipmentOutPicking(ModelView):
    'Shipment Out Picking'
    __name__ = 'stock.shipment.out.picking'
    shipment = fields.Many2One('stock.shipment.out', 'Shipment', required=True,
        domain=[('state', '=', 'assigned')],
        help="Shipment Assigned state")
    lines = fields.One2Many('stock.shipment.out.picking.line', None, 'Lines')


class ShipmentOutPickingLine(ModelView):
    'Shipment Out Picking Line'
    __name__ = 'stock.shipment.out.picking.line'
    product = fields.Many2One('product.product', 'Product')
    quantity = fields.Float('Quantity', digits=(16, 2))

    @staticmethod
    def default_quantity():
        return 1


class ShipmentOutPickingResult(ModelView):
    'Shipment Out Picking Result'
    __name__ = 'stock.shipment.out.picking.result'
    shipment = fields.Many2One('stock.shipment.out', 'Shipment', readonly=True)
    note = fields.Text('Note', readonly=True)


class ShipmentOutPacked(Wizard):
    'Shipment Out Packed'
    __name__ = 'stock.shipment.out.packed'
    start = StateTransition()
    picking = StateView('stock.shipment.out.picking',
        'stock_picking.stock_shipment_out_picking', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Picking', 'packed', 'tryton-ok', True),
            ])
    packed = StateTransition()
    result = StateView('stock.shipment.out.picking.result',
        'stock_picking.stock_shipment_out_picking_result', [
            Button('New picking', 'picking', 'tryton-go-next', True),
            Button('Done', 'end', 'tryton-ok'),
            ])

    @classmethod
    def __setup__(cls):
        super(ShipmentOutPacked, cls).__setup__()
        cls._error_messages.update({
            'not_product': 'Missing product "%(product)s" in shipment',
            'not_quantity': 'Does not match the quantity. Qty "%(product)s" '
                'is "%(quantity)s"',
        })

    def transition_start(self):
        return 'picking'

    def transition_packed(self):
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')

        shipment = self.picking.shipment
        lines = self.picking.lines

        shipment.picking_before(shipment)

        outgoing_moves = {}
        for move in shipment.outgoing_moves:
            if move.product.id in outgoing_moves:
                outgoing_moves[move.product.id] = move.quantity + outgoing_moves[move.product.id]
            else:
                outgoing_moves[move.product.id] = move.quantity

        picking_moves = {}
        for line in lines:
            if not line.product:
                continue
            if line.product.id in picking_moves:
                picking_moves[line.product.id] = line.quantity + picking_moves[line.product.id]
            else:
                picking_moves[line.product.id] = line.quantity

        # check if product is in shipment and quantity
        for k, v in outgoing_moves.iteritems():
            if not k in picking_moves:
                product, = [move.product.rec_name for move in shipment.outgoing_moves 
                    if move.product.id == k]
                self.raise_user_error('not_product', {
                        'product': product,
                        })
            if not v == picking_moves[k]:
                product, = [move.product.rec_name for move in shipment.outgoing_moves 
                    if move.product.id == k]
                self.raise_user_error('not_quantity', {
                        'product': product,
                        'quantity': v,
                        })

        # Change new state: assigned to packed
        Shipment.pack([shipment])
        Shipment.done([shipment])

        # Post actions
        note = Shipment.picking_after(shipment)

        self.result.shipment = shipment
        self.result.note = note
        return 'result'

    def default_result(self, fields):
        return {
            'shipment': self.result.shipment.id,
            'note': self.result.note,
            }
