#This file is part stock_picking module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.pyson import Eval

__all__ = ['ShipmentOut', 'ShipmentOutPicking', 'ShipmentOutPickingLine',
    'ShipmentOutPickingResult', 'ShipmentOutPacked',
    'ShipmentOutScanningStart', 'ShipmentOutScanningResult', 'ShipmentOutScanning']


class ShipmentOut(metaclass=PoolMeta):
    __name__ = 'stock.shipment.out'

    def picking_before(self):
        return

    def picking_after(self):
        return


class ShipmentOutPicking(ModelView):
    'Shipment Out Picking'
    __name__ = 'stock.shipment.out.picking'
    shipment = fields.Many2One('stock.shipment.out', 'Shipment', required=True,
        states={
            'readonly': (Eval('lines', [0]) & Eval('shipment')),
            },
        domain=[('state', 'in', ['assigned', 'packed'])],
        help="Shipment Assigned state")
    lines = fields.One2Many('stock.shipment.out.picking.line', 'shipment',
        'Lines')
    number_packages = fields.Integer('Number of Packages')
    note = fields.Text('Note', readonly=True,
        states={
            'invisible': ~Eval('note'),
            },
        )

    @staticmethod
    def default_number_packages():
        return 1

    @fields.depends('shipment')
    def on_change_shipment(self, name=None):
        notes = []
        if self.shipment:
            if hasattr(self.shipment, 'comment') and self.shipment.comment:
                notes.append(self.shipment.comment)
            if hasattr(self.shipment, 'carrier_notes') and self.shipment.carrier_notes:
                notes.append(self.shipment.carrier_notes)
        self.note = '\n'.join(notes)


class ShipmentOutPickingLine(ModelView):
    'Shipment Out Picking Line'
    __name__ = 'stock.shipment.out.picking.line'
    shipment = fields.Many2One('stock.shipment.out.picking', 'Shipment Out',
        required=True)
    product_domain = fields.Function(fields.One2Many('product.product', None,
        'Product Domain'), 'on_change_with_product_domain')
    product = fields.Many2One('product.product', 'Product',
        domain=[
            ('id', 'in', Eval('product_domain')),
        ], depends=['product_domain'])
    quantity = fields.Float('Quantity', digits=(16, 2))

    @fields.depends('shipment')
    def on_change_with_product_domain(self, name=None):
        if not self.shipment or not self.shipment.shipment:
            return []
        return [m.product.id for m in self.shipment.shipment.moves]

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
        'stock_picking.stock_shipment_out_picking_start', [
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
            'unknow_error': 'Unknown error. Try again to picking the shipment',
        })

    def transition_start(self):
        return 'picking'

    @classmethod
    def _shipment_data(cls, shipment, values={}):
        for k, v in values.items():
            setattr(shipment, k,  v)
        return shipment

    def transition_packed(self):
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')

        shipment = self.picking.shipment
        lines = self.picking.lines

        shipment.picking_before()

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
        unknow_error = False
        for k, v in outgoing_moves.items():
            if not k in picking_moves:
                products = [move.product.rec_name for move in shipment.outgoing_moves
                    if move.product.id == k]
                if products:
                    self.raise_user_error('not_product', {
                            'product': products[0],
                            })
                unknow_error = True
            if not v == picking_moves[k]:
                products = [move.product.rec_name for move in shipment.outgoing_moves
                    if move.product.id == k]
                if products:
                    self.raise_user_error('not_quantity', {
                            'product': products[0],
                            'quantity': v,
                            })
                unknow_error = True
        if unknow_error:
            self.raise_user_error('unknow_error')

        shipment = self._shipment_data(shipment, {
            'number_packages': self.picking.number_packages or 1,
            })
        shipment.save()

        # Change new state: assigned to packed
        Shipment.pack([shipment])
        shipment.picking_after()
        Shipment.done([shipment])

        note = None
        if hasattr(shipment, 'carrier_notes'):
            note = '%s\n' % shipment.carrier_notes
        self.result.note = note
        self.result.shipment = shipment
        return 'result'

    def default_picking(self, fields):
        Shipment = Pool().get('stock.shipment.out')

        if Transaction().context.get('active_id') and \
                Transaction().context.get('active_model') == 'stock.shipment.out':
            shipment = Shipment(Transaction().context['active_id'])
            if shipment.state == 'assigned':
                return {
                    'shipment': shipment.id,
                    }
        return {}

    def default_result(self, fields):
        return {
            'shipment': self.result.shipment.id,
            'note': self.result.note,
            }


class ShipmentOutScanningStart(ModelView):
    'Shipment Out Scanning Start'
    __name__ = 'stock.shipment.out.scanning.start'
    product = fields.Many2One('product.product', 'Product', required=True)
    shipments = fields.Many2Many('stock.shipment.out', None, None, 'Shipments',
        domain=[
            ('state', '=', 'assigned'),
        ], order=[('planned_date', 'ASC')])


class ShipmentOutScanningResult(ModelView):
    'Shipment Out Scanning Result'
    __name__ = 'stock.shipment.out.scanning.result'
    shipment = fields.Many2One('stock.shipment.out', 'Shipment', readonly=True)
    note = fields.Text('Note', readonly=True)


class ShipmentOutScanning(Wizard):
    'Shipment Out Scanning'
    __name__ = 'stock.shipment.out.scanning'
    start = StateView('stock.shipment.out.scanning.start',
        'stock_picking.stock_shipment_out_scanning_start', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Picking', 'packed', 'tryton-ok', default=True),
        ])
    packed = StateTransition()
    result = StateView('stock.shipment.out.scanning.result',
        'stock_picking.stock_shipment_out_scanning_result', [
            Button('New picking', 'start', 'tryton-go-next', True),
            Button('Done', 'end', 'tryton-ok'),
        ])

    def transition_packed(self):
        pool = Pool()
        ShipmentOut = pool.get('stock.shipment.out')
        ShipmentOutScanningStart = pool.get('stock.shipment.out.scanning.start')

        def picking_shipment(product, shipments):
            for shipment in shipments:
                outgoing_moves = shipment.outgoing_moves
                if len(outgoing_moves) > 1:
                    continue
                for move in outgoing_moves:
                    if move.quantity > 1.0:
                        continue
                    if move.product == product:
                        return shipment

        if self.start.shipments:
            shipments = self.start.shipments
        else:
            domain = ShipmentOutScanningStart.shipments.domain
            shipments = ShipmentOut.search(
                domain,
                order=[('planned_date', 'ASC')])

        shipment = picking_shipment(self.start.product, shipments)
        if not shipment:
            return 'start'
        # self.start.shipments = filter(lambda x: x != shipment,
        #     self.start.shipments)

        # Change new state: assigned to packed
        ShipmentOut.pack([shipment])
        shipment.picking_after()
        ShipmentOut.done([shipment])

        note = None
        if hasattr(shipment, 'carrier_notes') and shipment.carrier_notes:
            note = '%s\n' % shipment.carrier_notes
        self.result.note = note
        self.result.shipment = shipment
        return 'result'

    def default_start(self, fields):
        return {
            'shipments': None,
            }

    def default_result(self, fields):
        return {
            'shipment': self.result.shipment.id,
            'note': self.result.note,
            }
