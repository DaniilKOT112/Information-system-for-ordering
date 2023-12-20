from database import connection


def get_category_id(categories_name):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT id_categories 
                FROM categories 
                WHERE name_categories = %s;
                ''', (categories_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                return None
    except Exception as e:
        print(f'Ошибка: {e}')
        return None


def get_parent_category_id(parent_category_name):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT id_parent_category 
                FROM parent_category 
                WHERE name = %s;
                ''', (parent_category_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                return None
    except Exception as e:
        print(f'Ошибка: {e}')
        return None


def get_product_id(product_name):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT id_product 
                FROM product 
                WHERE name = %s;
                ''', (product_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                return None
    except Exception as e:
        print(f'Ошибка: {e}')
        return None


def get_image_for_product(name_product):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT I.url
                FROM product P
                JOIN image I ON P.id_image = I.id_image
                WHERE P.name LIKE %s::text;
            ''', (name_product,))

            image_url = cursor.fetchone()

            if image_url:
                return image_url[0]

    except Exception as e:
        print(f'Ошибка: {e}')
        return None


def get_product_price(product_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT price FROM product WHERE id_product = %s;', (product_id,))
        price = cursor.fetchone()[0]
    return price


def get_product_quantity(product_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT amount FROM product WHERE id_product = %s;', (product_id,))
        quantity = cursor.fetchone()[0]
    return quantity


def get_order_quantity(order_id, product_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT amount FROM order_details WHERE id_order = %s AND id_product = %s',
                       (order_id, product_id,))
        quantity = cursor.fetchone()[0]
    return quantity


def get_order_details(id_order):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT P.name, C.name_categories, OD.id_order, OD.amount, OD.price
                FROM order_details OD
                INNER JOIN product P ON OD.id_product = P.id_product
                INNER JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                JOIN categories C ON CPC.id_categories = C.id_categories
                WHERE OD.id_order = %s
            ''', (id_order,))

            order_details_data = cursor.fetchall()
            return order_details_data

    except Exception as e:
        print(f'Ошибка: {e}')
