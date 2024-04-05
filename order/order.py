#!/usr/bin/env python3
# The above shebang (#!) operator tells Unix-like environments
# to run this file as a python3 script

import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from random import randint
import json

from datetime import datetime

#regular Flask and SQLALCHEMY start
dbURL = os.environ.get('dbURL')
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = dbURL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

#creating tables

class Order(db.Model):
    __tablename__ = "order"

    order_id = db.Column(db.Integer, primary_key=True) #auto-increments
    customer_id = db.Column(db.String(255), nullable = False)
    customer_email = db.Column(db.String(255), nullable = False)
    status = db.Column(db.String(15), nullable = False) #shipped, processing, cancelled, pending
    created = db.Column(db.DateTime, nullable= False, default=datetime.now)
    modified = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    payment_status = db.Column(db.String(10), nullable = False) #paid, pending, failed #probaby FK from Payment
    shipping_address = db.Column(db.String(255), nullable = False, default = "81 Victoria St, Singapore 188065") 
    stripe_session_id = db.Column(db.String(255), nullable = False, default = "NA")
    
    order_items = relationship("Order_Item", cascade="all, delete-orphan")

    def json(self):
        dto = {
            'order_id': self.order_id,
            'customer_id': self.customer_id,
            'customer_email': self.customer_email,
            'status': self.status,
            'created': self.created,
            'modified': self.modified,
            'payment_status': self.payment_status,
            'shipping_address': self.shipping_address,
            "stripe_session_id": self.stripe_session_id
        }

        dto['order_item'] = []
        for oi in self.order_item:
            dto['order_item'].append(oi.json())

        return dto

class Order_Item(db.Model):
    __tablename__ = 'order_item'

    item_id = db.Column(db.Integer, primary_key=True) #auto-increments
    order_id = db.Column(db.ForeignKey(
        'order.order_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    game_id = db.Column(db.String(100), nullable = False) 
    game_name = db.Column(db.String(255), nullable = False)
    quantity = db.Column(db.Integer, nullable = False)
    price = db.Column(db.Float, nullable = False)
    price_id = db.Column(db.String(100), nullable = False)
    genre_string = db.Column(db.String(100), nullable = False)
    order = db.relationship(
        'Order', primaryjoin='Order_Item.order_id == Order.order_id', backref='order_item')

    def json(self):
        return {'item_id': self.item_id,
                'order_id': self.order_id,
                'game_id': self.game_id,
                'game_name': self.game_name,
                'quantity': self.quantity,
                'price': self.price,
                'price_id': self.price_id,
                'genre_string': self.genre_string
                }

@app.route("/order")
def get_all():
    orderlist = db.session.scalars(db.select(Order)).all()
    if len(orderlist):
        return jsonify(
            {
                "code": 200,
                "data": {
                    "orders": [order.json() for order in orderlist]
                }
            }
        )
    return jsonify(
        {
            "code": 404,
            "message": "There are no orders."
        }
    ), 404

@app.route("/orderbyid", methods=["POST"]) 
def find_by_order_id():
    order_id = request.json.get('order_id', None)
    order = db.session.scalars(
        db.select(Order).filter_by(order_id=order_id).limit(1)).first()

    if order:
        return jsonify(
            {
                "code": 200,
                "data": order.json()
            }
        )
    return jsonify(
        {
            "code": 404,
            "data": {
                "order_id": order_id
            },
            "message": "Order not found."
        }
    ), 404

@app.route("/order", methods=['POST'])
def create_order():
    customer_id = request.json.get('customer_id', None)
    customer_email = request.json.get('customer_email', None)
    shipping_address = request.json.get('shipping_address', None)
    order = Order(customer_id=customer_id, customer_email=customer_email, shipping_address=shipping_address, status='processing', payment_status='pending')

    cart_item = request.json.get('cart')
    for item in cart_item:
        genre_list = item.get("Genre") #convert genre_list to genre string for db storage
        genre_string = ""
        if genre_list:
            genre_string = ', '.join(genre_list)
        else:
            genre_string = ""

        order.order_item.append(Order_Item(
            game_id=item['_id'], game_name=item['GameName'], quantity=item['Quantity'], price=item['Price'] ,price_id=item['StripePrice']['id'], genre_string=genre_string))
    try:
        db.session.add(order)
        db.session.commit()
    except Exception as e:
        return jsonify(
            {
                "code": 500,
                "message": "An error occurred while creating the order. " + str(e)
            }
        ), 500

    return jsonify(
        {
            "code": 201,
            "data": order.json()
        }
    ), 201

@app.route("/cidbygame", methods=['POST'])
def cidbyagame():
    game_id = request.json.get('game_id', None)
    orderlist = db.session.scalars(db.select(Order)).all()
    filtered_orders = []
    customer_id_list = []
    game_quantity_list = []
    for order in orderlist:
        for item in order.order_item:
            if item.game_id == game_id:
                filtered_orders.append(order.json())
                customer_id_list.append(order.customer_id)
                game_quantity_list.append(item.quantity)

    if len(filtered_orders) > 0:
        return jsonify(
            {
                "code": 200,
                "data": {
                    "orders": filtered_orders
                }
            }
        )
    return jsonify(
        {
            "code": 404,
            "message": "There are no orders."
        }
    ), 404

@app.route("/orderlist", methods=['POST'])
def orderlistbycid():
    customer_id = request.json.get('customer_id', None)
    orderlist = db.session.scalars(db.select(Order)).all()
    filtered_orders = []
    game_id_list = []
    game_name_list = []
    genre_string = ""
    customer_email = ""
    for order in orderlist:
        if order.customer_id == customer_id:
            filtered_orders.append(order.json())
            for item in order.order_item:
                game_id_list.append(item.game_id)
                game_name_list.append(item.game_name)
                genre_string = item.genre_string
            customer_email = order.customer_email
                   
    if len(filtered_orders) > 0:
        return {"customer_id": customer_id,"customer_email":customer_email ,"game_list": game_id_list, "game_name_list": game_name_list, "genre_string": genre_string}
    return  jsonify(
        {
            "code": 404,
            "message": "This user have not made not any orders."
        }
    ), 404

@app.route("/updateprice", methods=['PUT'])
def updateprice():
    order_id = request.json.get('order_id', None)
    game_id = request.json.get('game_id', None)  # Corrected key
    new_price = request.json.get('new_price', None)  # Corrected key

    order = db.session.query(Order).filter_by(order_id=order_id).first()  # Corrected query

    if order:
        order_item = db.session.query(Order_Item).filter_by(order_id=order_id).first()
        if order_item:
            order_item.price = new_price  # Update price
            db.session.commit()  # Commit changes to the database
            return jsonify({
                "code": 200,
                "data": order.json()
            })
        else:
            return jsonify({
                "code": 404,
                "data": {
                    "order_id": order_id,
                    "item_id": item_id
                },
                "message": "Order item not found."
            }), 404
    else:
        return jsonify({
            "code": 404,
            "data": {
                "order_id": order_id
            },
            "message": "Order not found."
        }), 404


@app.route("/removeorder", methods=['POST'])
def removeorderbyoid():
    order_id = request.json.get('order_id', None)
    order_to_delete = Order.query.filter(Order.order_id == order_id).one_or_none()
    
    if order_to_delete is None:
        return jsonify(
            {
                "code": 404,
                "message": f"Order with ID {order_id} not found."
            }
        ), 404
    
    try:
        db.session.delete(order_to_delete)
        db.session.commit()
    except Exception as e:
        return jsonify(
            {
                "code": 500,
                "message": "An error occurred while removing the order. " + str(e)
            }
        ), 500

    return jsonify(
        {
            "code": 201,
            "message": "Successfully removed order " + str(order_id)
        }
    ), 201

@app.route('/order/stripe_session', methods=['POST'])
def update_stripe_session():
    # Get the order_id and stripe_session_id from the request body
    order_id = request.json.get('order_id')
    stripe_session_id = request.json.get('session_id')

    # If the order_id or stripe_session_id is not provided, return an error
    if order_id is None:
        return jsonify({'error': 'order_id is required'}), 400
    if stripe_session_id is None:
        return jsonify({'error': 'stripe_session_id is required'}), 400

    # Get the order by id
    order = Order.query.get(order_id)

    # If the order doesn't exist, return an error
    if order is None:
        return jsonify({'error': 'Order not found'}), 404

    # Update the order's stripe_session_id
    order.stripe_session_id = stripe_session_id
    order.payment_status = 'paid'
    db.session.commit()

    # Return the updated order
    return jsonify(order.json()), 200

@app.route('/update_payment', methods=['POST'])
def update_payment_status():
    # Get the order_id and stripe_session_id from the request body
    order_id = request.json.get('order_id')
    payment_status = request.json.get('payment_status')

    # If the order_id or stripe_session_id is not provided, return an error
    if order_id is None:
        return jsonify({'error': 'order_id is required'}), 400
    if payment_status is None:
        return jsonify({'error': 'payment_status is required'}), 400

    # Get the order by id
    order = Order.query.get(order_id)

    # If the order doesn't exist, return an error
    if order is None:
        return jsonify({'error': 'Order not found'}), 404

    # Update the order's stripe_session_id
    order.payment_status = payment_status
    db.session.commit()

    # Return the updated order
    return jsonify(order.json()), 200

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    print("This is flask for " + os.path.basename(__file__) + ": manage orders ...")
    app.run(host='0.0.0.0', port=5000, debug=True)