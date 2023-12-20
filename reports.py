from PyQt5.QtGui import QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import QFileDialog

from database import connection


def product_quantity():
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT id_product, name, amount
                FROM product
            ''')
            result = cursor.fetchall()
            products = []
            for row in result:
                product_id, product_name, quantity = row
                products.append({'id_product': product_id, 'name': product_name, 'quantity': quantity})
            return products

    except Exception as e:
        print(f'Ошибка: {e}')


def product_quantity_date(selected_date):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT O.order_date, P.name, OD.amount, C.name_categories, OD.price
                FROM "order" O
                JOIN order_details OD ON O.id_order = OD.id_order
                JOIN product P ON OD.id_product = P.id_product
                JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                JOIN categories C ON CPC.id_categories = C.id_categories
                WHERE O.order_date = %s
            ''', (selected_date,))
            return cursor.fetchall()
    except Exception as e:
        print(f'Ошибка: {e}')


def categories_parents():
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT C.name_categories, PC.name
                FROM categories_parent_category CPC
                JOIN categories C ON CPC.id_categories = C.id_categories
                JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                ORDER BY C.name_categories
            ''')
            return cursor.fetchall()

    except Exception as e:
        print(f'Ошибка: {e}')


def categories_count():
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT name_categories, COUNT(*) AS category_count
                FROM categories
                GROUP BY name_categories;
            ''')
            return cursor.fetchall()

    except Exception as e:
        print(f'Ошибка: {e}')


def order_count():
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT id_order, order_date, COUNT(*) AS record_count
                FROM "order"
                GROUP BY id_order;
            ''')
            return cursor.fetchall()

    except Exception as e:
        print(f'Ошибка: {e}')


def generate_pdf(order_id, order_pdf):
    pdf_file, _ = QFileDialog.getSaveFileName(None, 'Save PDF', '', 'PDF files (*.pdf)')
    if pdf_file:
        try:
            doc = QTextDocument()
            content = f'ID заказа: {order_id}\n\nПозиции заказа:\n'
            total_sum = 0
            for detail in order_pdf:
                product_name, product_id, amount, price_str = detail
                price = float(price_str.replace('$', ''))
                content += f'ID_товара: {product_id}\n'
                content += f'Наименование товара: {product_name}\n'
                content += f'Количество товара: {amount}\n'
                content += f'Цена: ${price:.2f}\n\n'
                total_sum += price

            content += f'Итоговая сумма: ${total_sum:.2f}\n'

            doc.setPlainText(content)
            printer = QPrinter(QPrinter.PrinterResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_file)
            doc.print_(printer)

        except Exception as e:
            print(f'Ошибка: {e}')


def create_pdf_report(content):
    try:
        pdf_file, _ = QFileDialog.getSaveFileName(None, 'Save PDF', '', 'PDF files (*.pdf)')
        if pdf_file:
            doc = QTextDocument()
            doc.setPlainText(content)
            printer = QPrinter(QPrinter.PrinterResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_file)
            doc.print_(printer)

    except Exception as e:
        print(f'Ошибка: {e}')
