#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from decimal import Decimal
from functools import reduce
from trytond.model import ModelView, ModelSQL, fields, OPERATORS
from trytond.backend import TableHandler
from trytond.transaction import Transaction
from trytond.pool import Pool
from trytond.pyson import In, Eval, Not, Equal, If, Get, Bool

STATES = {
    'readonly': In(Eval('state'), ['cancel', 'assigned', 'done']),
}
DEPENDS = ['state']


class Move(ModelSQL, ModelView):
    _name = 'stock.move'

    sequence = fields.Integer('Sequence')
    kit_depth = fields.Integer('Depth', required=True, 
            help='Depth of the line if it is part of a kit.')
    kit_parent_line = fields.Many2One('stock.move', 'Parent Kit Line', 
            help='The kit that contains this product.')
    kit_child_lines = fields.One2Many('stock.move', 'kit_parent_line', 
            'Lines in the kit', help='Subcomponents of the kit.')

    def __init__(self):
        super(Move, self).__init__()
        self._order.insert( 0, ('id','ASC'))

    def default_kit_depth(self):
        return 0

    def get_kit_line(self, line, kit_line, depth):
        """
        Given a line browse object and a kit dictionary returns the
        dictionary of fields to be stored in a create statement.
        """
        res = {}
        uom_obj = Pool().get('product.uom')        
        quantity = uom_obj.compute_qty(kit_line.unit,
                        kit_line.quantity, line.uom) * line.quantity

        res['sequence'] = line.id + depth
        res['product'] = kit_line.product.id
        res['quantity'] = quantity
        res['from_location'] = line.from_location.id
        res['to_location'] = line.to_location.id
        res['unit_price'] = line.unit_price
        res['kit_depth'] = depth
        res['kit_parent_line'] = line.id
        res['planned_date'] = False
        res['company'] = line.company.id
        res['uom'] = line.uom.id
        res['shipment_out'] = line.shipment_out and \
                              line.shipment_out.id  or False
        res['shipment_in'] = line.shipment_in and \
                             line.shipment_in.id or False
        res['shipment_out_return'] = line.shipment_out_return  and \
                                     line.shipment_out_return.id or False
        res['shipment_in_return'] = line.shipment_in_return and \
                                    line.shipment_in_return.id or False
        res['shipment_internal'] = line.shipment_internal and \
                                   line.shipment_internal or False
        
        return res

    def explode_kit(self, id, depth=1):
        """
        Walks through the Kit tree in depth-first order and returns
        a sorted list with all the components of the product.
        """
        line = self.browse(id)

        result = []

        print "EXPLODE"
        
        """ Check if kit has been already expanded """
        if line.kit_child_lines:
            return result

        """ Explode kit """
        for kit_line in line.product.kit_lines:
            values = self.get_kit_line(line, kit_line, depth)
            new_id = self.create(values)
            
            self.explode_kit(new_id, depth+1)
        return result

    def create(self, values):
        id = super(Move, self).create(values)
        self.explode_kit(id)
        return id

    def kit_tree_ids(self, line):
        res = []
        for kit_line in line.kit_child_lines:
            res.append(kit_line.id)
            res += self.kit_tree_ids(kit_line)
        return res

    def write(self, ids, values):
        """ Regenerate kit if quantity, product or unit has changed """
        
        reset_kit = False
        if 'product' in values or 'quantity' in values or 'unit' in values:
            reset_kit = True

        if isinstance(ids, (int, long)):
            ids = [ids]
        ids = ids[:]

        if reset_kit:
            to_delete = []
            for line in self.browse(ids):
                to_delete += self.kit_tree_ids(line)
            self.delete(to_delete)
            ids = list(set(ids) - set(to_delete))
        res = super(Move, self).write(ids, values)
        if reset_kit:
            for id in ids:
                self.explode_kit(id)
        return res

    def delete( self, ids):
        """ Check if stock move to delete belongs to kit."""
        ids = ids[:]
        
        for line in self.browse(ids):
            if line.kit_parent_line:
                continue
                
            if line.kit_child_lines:
                """ Removing kit, adding all childs products to delete"""
                ids += self.kit_tree_ids(line)

        return super(Move,self).delete(ids)
        

Move()
