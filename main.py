import psycopg2
import base64
import os
import sys

from functools import partial
from PyQt5.QtCore import QPropertyAnimation, QSize, QRegExp, Qt, QUrl
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QPixmap, QRegExpValidator, QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QPushButton, QHeaderView, QFileDialog, QLabel

from database import connection
from ui_main import Ui_MainWindow
from qt_material import apply_stylesheet
from get import get_category_id, get_parent_category_id, get_image_for_product, get_product_id, get_product_price, \
    get_product_quantity, get_order_quantity

directory = os.path.abspath(os.curdir)
russian_validator = QRegExpValidator(QRegExp('[А-Яа-яЁё ]+'))
real = QRegExpValidator(QRegExp('^[0-9]+(\.[0-9]{1,2})?$'))
integer = QRegExpValidator(QRegExp('^[0-9]+$'))


def show_error_message(message):
    msg = QMessageBox()
    msg.setWindowIcon(QIcon(directory + f'/icon/danger.png'))
    msg.setIcon(QMessageBox.Warning)
    msg.setStyleSheet('background-color: rgb(94, 94, 94)')
    msg.setText(message)
    msg.setWindowTitle("Сообщение об ошибке")
    msg.exec_()


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
                total_sum += amount * price

            content += f'Итоговая сумма: ${total_sum:.2f}\n'

            doc.setPlainText(content)
            printer = QPrinter(QPrinter.PrinterResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_file)
            doc.print_(printer)

        except Exception as e:
            print(f'Error: {e}')


def update_product_amount(product_id, delta):
    with connection.cursor() as cursor:
        cursor.execute('''
            UPDATE product
            SET amount = amount - %s
            WHERE id_product = %s
        ''', (delta, product_id))

    connection.commit()


def update_quantity(row, delta, model):
    try:
        amount_item = model.item(row, 3)
        amount_text = amount_item.text()
        amount = int(amount_text) if amount_text else 0
        product_name = model.item(row, 0).text()
        product_id = get_product_id(product_name)
        quantity = get_product_quantity(product_id)
        price_text = get_product_price(product_id)
        price = float(price_text.replace('$', '')) if price_text else 0.0

        new_amount = max(amount + delta, 0)

        if new_amount > quantity:
            show_error_message('На складе недостаточно товара для совершения заказа, пожалуйста попробуйте позже')
            return

        amount_item.setText(str(new_amount))
        total_price = new_amount * price
        total_price_item = model.item(row, 5)
        total_price_item.setText('${:.2f}'.format(total_price))

    except Exception as e:
        print(f'Ошибка: {e}')


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.initial_quantities = None
        self.image_file_2 = None
        self.current_edit_parent_categories_id = None
        self.current_edit_categories_id = None
        self.vertical_header = None
        self.horizontal_header = None
        self.header = None
        self.animation = None
        self.image_file = None
        self.new_order_id = None

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.Widget_pages.setCurrentWidget(self.ui.pageCatalog)

        self.ui.frameLeftMenu.enterEvent = self.enter_event_handler
        self.ui.frameLeftMenu.leaveEvent = self.leave_event_handler

        self.ui.catalog.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCatalog))
        self.ui.products.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageProduct))
        self.ui.orders.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageOrderList))
        self.ui.reports.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageReports))
        self.ui.categories.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCategories))
        self.ui.addProductList.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageAddProduct))
        self.ui.cancelProduct.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageProduct))
        self.ui.cancelInfoOrder_2.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageOrderList))
        self.ui.addCategoriesList.clicked.connect(
            partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageAddCategories))
        self.ui.cancelCategories.clicked.connect(
            partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCategories))
        self.ui.cancelEditCategories.clicked.connect(
            partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCategories))
        self.ui.cancelEditProduct.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageProduct))
        self.ui.tableProductOrder.doubleClicked.connect(self.double_click_add)
        self.ui.tableCatalogOrder.doubleClicked.connect(self.double_click_dell)

        self.ui.applyEditProduct.clicked.connect(self.update_product)
        self.ui.search.clicked.connect(self.search_product)
        self.ui.filters.clicked.connect(self.apply_function)
        self.filter_enabled = False

        self.ui.addCategories.clicked.connect(self.insert_data_categories)
        self.ui.addProduct.clicked.connect(self.insert_data_product)
        self.ui.applyEditCategories.clicked.connect(self.update_categories)

        self.ui.textEditImageProduct.mousePressEvent = self.open_image_dialog

        self.model_table_categories = QStandardItemModel()
        self.ui.tableAddCategories.setModel(self.model_table_categories)
        self.model_table_product = QStandardItemModel()
        self.ui.tableProductOrder.setModel(self.model_table_product)
        self.model_table_main_product = QStandardItemModel()
        self.ui.tableProduct.setModel(self.model_table_main_product)
        self.model_table_orders = QStandardItemModel()
        self.ui.tableCatalogOrder.setModel(self.model_table_orders)
        self.model_table_main_orders = QStandardItemModel()
        self.ui.listOrder.setModel(self.model_table_main_orders)
        self.model_table_edit_order = QStandardItemModel()
        self.ui.editOrder.setModel(self.model_table_edit_order)

        self.filter_product()
        self.get_data_main_product()
        self.get_categories_parent_category()
        self.get_categories_parent_category_2()
        self.get_data_product()
        self.get_data_categories()
        self.get_categories()
        self.get_data_orders()

        self.ui.comboBox_categories.setEnabled(False)

        self.ui.lineEditNameCategory.setValidator(russian_validator)
        self.ui.lineEditNameCategory_2.setValidator(russian_validator)
        self.ui.lineEditParentCategory.setValidator(russian_validator)
        self.ui.lineEditParentCategory_2.setValidator(russian_validator)
        self.ui.lineEditNameProduct.setValidator(russian_validator)
        self.ui.lineEditNameProduct_2.setValidator(russian_validator)
        self.ui.lineEditSearch.setValidator(russian_validator)

        self.ui.lineEditAmountProduct.setValidator(integer)
        self.ui.lineEditAmountProduct_2.setValidator(integer)
        self.ui.lineEditPriceProduct.setValidator(real)
        self.ui.lineEditPriceProduct_2.setValidator(real)

        self.ui.placeOrder.clicked.connect(self.order_button_clicked)
        self.ui.applyEditOrder.clicked.connect(self.edit_order)

        self.rows = []
        self.updates = []

    def update_quantity_2(self, row, delta, model):
        selected_row = self.ui.listOrder.currentIndex().row()
        order_item = self.model_table_main_orders.item(selected_row, 0)

        if order_item and order_item.text() is not None:
            order_item_text = order_item.text()
            try:
                product_name_item = model.item(row, 0)
                product_name = product_name_item.text()
                product_id = get_product_id(product_name)
                amount_item = model.item(row, 3)
                current_quantity = int(amount_item.text())
                new_amount = current_quantity + delta
                quantity = get_product_quantity(product_id)
                order_quantity = get_order_quantity(order_item_text, product_id)

                if new_amount < 0:
                    show_error_message('Количество товара не может быть отрицательным')
                    return

                if new_amount - order_quantity > quantity:
                    show_error_message('На складе недостаточно товара')
                    return

                with connection.cursor() as cursor:
                    cursor.execute('''
                        SELECT price
                        FROM product
                        WHERE id_product = %s
                    ''', (product_id,))
                    result = cursor.fetchone()
                    price_text = result[0] if result else '0.0'

                price = float(price_text.replace('$', '').replace(',', '').strip())

                self.updates.append({
                    'product_id': product_id,
                    'delta': delta,
                    'new_amount': new_amount,
                    'price': price
                })

                amount_item.setText(str(new_amount))
                total_price_item = model.item(row, 5)
                total_price = new_amount * price
                total_price_item.setText('${:.2f}'.format(total_price))

            except Exception as e:
                print(f'Ошибка: {e}')

    # def edit_order(self):
    #     selected_row = self.ui.listOrder.currentIndex().row()
    #     order_item = self.model_table_main_orders.item(selected_row, 0)
    #
    #     if order_item and order_item.text() is not None:
    #         order_item_text = order_item.text()
    #         try:
    #             with connection.cursor() as cursor:
    #                 for row_index in self.rows:
    #                     product = self.model_table_edit_order.item(row_index, 0)
    #                     product_name = product.text()
    #                     product_id = get_product_id(product_name)
    #
    #                     if product and product.text() is not None:
    #                         cursor.execute('''
    #                             SELECT amount
    #                             FROM order_details
    #                             WHERE id_order = %s AND id_product = %s
    #                         ''', (order_item_text, product_id))
    #
    #                         existing_quantity = cursor.fetchone()[0] if cursor.rowcount > 0 else 0
    #
    #                         new_amount = int(self.model_table_edit_order.item(row_index, 3).text())
    #                         delta = new_amount - existing_quantity
    #                         price_text = self.model_table_edit_order.item(row_index, 5).text()
    #                         price = float(price_text.replace('$', '').replace(',', '').strip())
    #
    #                         cursor.execute('''
    #                             UPDATE order_details
    #                             SET amount = %s, price = %s
    #                             WHERE id_order = %s AND id_product = %s
    #                         ''', (new_amount, price, order_item_text, product_id))
    #
    #                         update_product_amount(product_id, delta)
    #
    #                 connection.commit()
    #             self.ui.Widget_pages.setCurrentWidget(self.ui.pageOrderList)
    #             self.get_data_product()
    #
    #         except Exception as e:
    #             print(f'Ошибка: {e}')

    def edit_order(self):
        selected_row = self.ui.listOrder.currentIndex().row()
        order_item = self.model_table_main_orders.item(selected_row, 0)

        if order_item and order_item.text() is not None:
            order_item_text = order_item.text()
            try:
                with connection.cursor() as cursor:
                    for row_index in self.rows:
                        product = self.model_table_edit_order.item(row_index, 0)
                        product_name = product.text()
                        product_id = get_product_id(product_name)

                        if product and product.text() is not None:
                            cursor.execute('''
                                SELECT amount
                                FROM order_details
                                WHERE id_order = %s AND id_product = %s
                            ''', (order_item_text, product_id))

                            existing_quantity = cursor.fetchone()[0] if cursor.rowcount > 0 else 0

                            new_amount_item = self.model_table_edit_order.item(row_index, 3)
                            new_amount = int(
                                new_amount_item.text()) if new_amount_item and new_amount_item.text() else 0

                            price_item = self.model_table_edit_order.item(row_index, 5)
                            price_text = price_item.text() if price_item and price_item.text() else '0'
                            price = float(price_text.replace('$', '').replace(',', '').strip())

                            if new_amount_item is not None and price_item is not None:
                                cursor.execute('''
                                    UPDATE order_details
                                    SET amount = %s, price = %s
                                    WHERE id_order = %s AND id_product = %s
                                ''', (new_amount, price, order_item_text, product_id))

                                update_product_amount(product_id, new_amount - existing_quantity)
                            else:
                                print(f"Skipping row {row_index} due to None values")

                    connection.commit()
                self.ui.Widget_pages.setCurrentWidget(self.ui.pageOrderList)
                self.get_data_product()

            except Exception as e:
                print(f'Ошибка: {e}')

    def edit_product_order(self):
        self.ui.Widget_pages.setCurrentWidget(self.ui.pageEditOrder)
        selected_row = self.ui.listOrder.currentIndex().row()
        order_item = self.model_table_main_orders.item(selected_row, 0)

        if order_item and order_item.text() is not None:
            order_item_text = order_item.text()

            try:
                with connection.cursor() as cursor:
                    cursor.execute('''
                        SELECT P.name, C.name_categories, OD.amount, OD.price
                        FROM order_details OD
                        INNER JOIN product P ON OD.id_product = P.id_product
                        INNER JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                        JOIN categories C ON CPC.id_categories = C.id_categories
                        WHERE OD.id_order = %s
                    ''', (order_item_text,))

                    order_details_data = cursor.fetchall()

                    self.model_table_edit_order.clear()
                    self.ui.editOrder.setModel(self.model_table_edit_order)
                    self.model_table_edit_order.setColumnCount(6)
                    self.model_table_edit_order.setHorizontalHeaderLabels(
                        ['Наименование', 'Категория', '', 'Количество', '', 'Цена'])

                    for row, details in enumerate(order_details_data, start=1):
                        self.model_table_edit_order.appendRow([
                            QStandardItem(str(details[0])),
                            QStandardItem(str(details[1])),
                            QStandardItem(''),
                            QStandardItem(str(details[2])),
                            QStandardItem(''),
                            QStandardItem(str(details[3]))
                        ])

                        index = self.model_table_edit_order.rowCount() - 1

                        for i in range(0, 6):
                            if i not in [2, 4]:
                                self.ui.editOrder.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
                            else:
                                self.ui.editOrder.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
                                self.ui.editOrder.horizontalHeader().resizeSection(i, 65)

                        button_plus = QPushButton(self)
                        button_plus.setFixedSize(60, 60)
                        button_plus.setIcon(QIcon(QPixmap(directory + '/icon/plus.png').scaled(QSize(60, 60))))
                        button_plus.clicked.connect(
                            lambda _, r=index: self.update_quantity_2(r, 1, self.model_table_edit_order))
                        self.ui.editOrder.setIndexWidget(self.model_table_edit_order.index(index, 2), button_plus)

                        button_minus = QPushButton(self)
                        button_minus.setFixedSize(60, 60)
                        button_minus.setIcon(QIcon(QPixmap(directory + '/icon/minus.png').scaled(QSize(60, 60))))
                        button_minus.clicked.connect(
                            lambda _, r=index: self.update_quantity_2(r, -1, self.model_table_edit_order))
                        self.ui.editOrder.setIndexWidget(self.model_table_edit_order.index(index, 4), button_minus)
                        self.ui.editOrder.verticalHeader().setDefaultSectionSize(65)

                        self.rows.append(index)

            except Exception as e:
                print(f'Ошибка: {e}')

    def delete_order(self):
        try:
            with connection.cursor() as cursor:
                selected_row = self.ui.listOrder.currentIndex().row()
                order_item = self.model_table_main_orders.item(selected_row, 0)

                if order_item and order_item.text() is not None:
                    order_item_text = order_item.text()

                cursor.execute('''
                       DELETE FROM "order" 
                       WHERE id_order = %s;
                   ''', (order_item_text,))

                connection.commit()
        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при удалении записи.')

        finally:
            self.get_data_orders()

    def get_data_orders(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT O.id_order, O.order_date
                    FROM "order" O
                    ORDER BY O.id_order;
                ''')
                records = cursor.fetchall()
                del_records = []

                self.model_table_main_orders.clear()
                self.model_table_main_orders.setColumnCount(4)
                self.model_table_main_orders.setHorizontalHeaderLabels(
                    ['Номер заказа', 'Дата заказа', '', ''])
                self.horizontal_header = self.ui.listOrder.horizontalHeader()

                for i in range(0, 2):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Stretch)

                for i in range(2, 4):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Fixed)
                    self.horizontal_header.resizeSection(i, 65)

                for record in records:
                    id_order = record[0]

                    cursor.execute('''
                        SELECT COUNT(*) 
                        FROM order_details 
                        WHERE id_order = %s
                    ''', (id_order,))

                    order = cursor.fetchone()[0] > 0

                    if not order:
                        cursor.execute('''
                            DELETE FROM "order" 
                            WHERE id_order = %s
                        ''', (id_order,))
                        connection.commit()
                    else:
                        del_records.append(record)

                for index, record in enumerate(del_records, start=1):
                    self.model_table_main_orders.appendRow([])
                    for col, value in enumerate(record):
                        item = QStandardItem(str(value))
                        self.model_table_main_orders.setItem(index - 1, col, item)

                    edit_button = QPushButton(self)
                    edit_button.setFixedSize(60, 60)
                    edit_button.setIcon(QIcon(
                        QPixmap(directory + f'/icon/edit.png').scaled(QSize(60, 60))))
                    edit_button.clicked.connect(lambda _, i=index - 1: self.edit_product_order())
                    self.ui.listOrder.setIndexWidget(self.model_table_main_orders.index(index - 1, 2),
                                                     edit_button)
                    delete_button = QPushButton(self)
                    delete_button.setFixedSize(60, 60)
                    delete_button.setIcon(QIcon(QPixmap(directory + f'/icon/delete.png').scaled(QSize(60, 60))))
                    delete_button.clicked.connect(lambda _, i=index - 1: self.delete_order())
                    self.ui.listOrder.setIndexWidget(self.model_table_main_orders.index(index - 1, 3),
                                                     delete_button)
                self.ui.listOrder.verticalHeader().setDefaultSectionSize(65)

        except Exception as e:
            print(f'Ошибка: {e}')

    def double_click_add(self, index):
        selected_row = index.row()
        self.add_product_order(selected_row)

    def double_click_dell(self, index):
        selected_row = index.row()
        self.remove_product_order(selected_row)

    def remove_product_order(self, row):
        try:
            product_name = self.model_table_orders.item(row, 0)
            category_name = self.model_table_orders.item(row, 1)
            product_name = str(product_name.text())
            category_name = str(category_name.text())

            for row in range(self.model_table_orders.rowCount() - 1, -1, -1):
                if str(self.model_table_orders.item(row, 0).text()) == product_name and str(
                        self.model_table_orders.item(row, 1).text()) == category_name:
                    self.model_table_orders.removeRow(row)
                    break

        except Exception as e:
            print(f'Ошибка: {e}')

    def add_product_order(self, row):
        try:
            product_name = self.model_table_product.item(row, 0)
            category_name = self.model_table_product.item(row, 2)
            product_name = str(product_name.text())
            category_name = str(category_name.text())

            for row in range(self.model_table_orders.rowCount()):
                if str(self.model_table_orders.item(row, 0).text()) == product_name \
                        and str(self.model_table_orders.item(row, 1).text()) == category_name:
                    show_error_message('Товар уже имеется в заказе!')
                    return

            amount = self.model_table_product.item(row, 5)
            price = self.model_table_product.item(row, 4)

            self.model_table_orders.appendRow([
                QStandardItem(product_name),
                QStandardItem(category_name),
                QStandardItem(''),
                QStandardItem(amount),
                QStandardItem(''),
                QStandardItem(price)
            ])
            self.model_table_orders.setHorizontalHeaderLabels(
                ['Наименование', 'Категория', '', 'Количество', '', 'Цена'])

            index = self.model_table_orders.rowCount() - 1

            for i in range(0, 6):
                if i not in [2, 4]:
                    self.ui.tableCatalogOrder.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
                else:
                    self.ui.tableCatalogOrder.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
                    self.ui.tableCatalogOrder.horizontalHeader().resizeSection(i, 65)

            button_plus = QPushButton(self)
            button_plus.setFixedSize(60, 60)
            button_plus.setIcon(QIcon(QPixmap(directory + '/icon/plus.png').scaled(QSize(60, 60))))
            button_plus.clicked.connect(lambda _, r=index: update_quantity(r, 1, self.model_table_orders))
            self.ui.tableCatalogOrder.setIndexWidget(self.model_table_orders.index(index, 2), button_plus)

            button_minus = QPushButton(self)
            button_minus.setFixedSize(60, 60)
            button_minus.setIcon(QIcon(QPixmap(directory + '/icon/minus.png').scaled(QSize(60, 60))))
            button_minus.clicked.connect(lambda _, r=index: update_quantity(r, -1, self.model_table_orders))
            self.ui.tableCatalogOrder.setIndexWidget(self.model_table_orders.index(index, 4), button_minus)

        except Exception as e:
            print(f'Ошибка: {e}')

    def order_button_clicked(self):
        if self.model_table_orders.rowCount() == 0:
            show_error_message('Пожалуйста добавьте продукт для оформления заказа!')
            return

        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO "order" (order_date) 
                    VALUES (CURRENT_DATE) 
                    RETURNING id_order;
                    ''')
                new_order_id = cursor.fetchone()[0]

                order_pdf = []

                for row in range(self.model_table_orders.rowCount()):
                    product_name = self.model_table_orders.item(row, 0).text()
                    amount = int(self.model_table_orders.item(row, 3).text())
                    price = self.model_table_orders.item(row, 5).text()
                    product_id = get_product_id(product_name)
                    current_quantity = get_product_quantity(product_id)
                    order_pdf.append((product_name, product_id, amount, price))

                    new_quantity = current_quantity - amount
                    cursor.execute('''
                        UPDATE product 
                        SET amount = %s 
                        WHERE id_product = %s;
                    ''', (new_quantity, product_id))

                    cursor.execute('''
                        SELECT id_product
                        FROM order_details
                        WHERE id_order = %s AND id_product = %s;
                    ''', (new_order_id, product_id))

                    existing_entry = cursor.fetchone()

                    if not existing_entry:
                        cursor.execute('''
                            INSERT INTO order_details (id_order, id_product, amount, price)
                            VALUES (%s, %s, %s, %s);
                        ''', (new_order_id, product_id, amount, price))

                connection.commit()

                self.model_table_orders.clear()
                self.model_table_orders.setColumnCount(6)
                self.model_table_orders.setHorizontalHeaderLabels(
                    ['Наименование', 'Категория', '', 'Количество', '', 'Цена'])

                for i in range(0, 6):
                    if i not in [2, 4]:
                        self.ui.tableCatalogOrder.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
                    else:
                        self.ui.tableCatalogOrder.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
                        self.ui.tableCatalogOrder.horizontalHeader().resizeSection(i, 65)

                self.get_data_product()
                self.get_data_main_product()
                self.get_data_orders()

                generate_pdf(new_order_id, order_pdf)
        except Exception as e:
            print(f'Ошибка: {e}')

    def open_image_dialog_2(self, event):
        if event.button() == Qt.LeftButton:
            image_file, _ = QFileDialog.getOpenFileName(self, 'Select Image', '',
                                                        'Image Files (*.png *.jpg *.bmp *.gif *.jpeg)')
            if image_file:
                self.image_file_2 = image_file
                url = QUrl.fromLocalFile(image_file)
                image_html = f'<img src="{url.toString()}" width="370">'
                self.ui.textEditImageProduct_2.clear()
                self.ui.textEditImageProduct_2.append(image_html)

    def open_image_dialog(self, event):
        if event.button() == Qt.LeftButton:
            image_file, _ = QFileDialog.getOpenFileName(self, 'Select Image', '',
                                                        'Image Files (*.png *.jpg *.bmp *.gif *.jpeg)')
            if image_file:
                url = QUrl.fromLocalFile(image_file)
                image_html = f'<img src="{url.toString()}" width="370">'
                self.ui.textEditImageProduct.clear()
                self.ui.textEditImageProduct.append(image_html)
                self.image_file = image_file

    def apply_function(self):
        if self.filter_enabled:
            self.ui.comboBox_categories.setEnabled(False)
            self.filter_enabled = False
            self.get_data_product()
        else:
            self.ui.comboBox_categories.setEnabled(True)
            self.filter_enabled = True
            self.filter_product()
            self.get_categories()

    def selected_category_products(self):
        selected_category = self.ui.comboBox_categories.currentText()
        if selected_category:
            self.filter_enabled = True
            self.filter_product()

    def get_categories(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT name_categories 
                    FROM categories 
                    ORDER BY name_categories;
                    ''')
                categories = cursor.fetchall()
                self.ui.comboBox_categories.clear()
                self.ui.comboBox_categories.addItems([category[0] for category in categories])
                self.ui.comboBox_categories.currentIndexChanged.connect(self.selected_category_products)

        except Exception as e:
            print(f'Ошибка: {e}')

    def get_categories_parent_category(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT C.name_categories, PC.name
                    FROM categories_parent_category CPC
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    ORDER BY C.name_categories;
                ''')
                categories = cursor.fetchall()

                self.ui.comboBoxCategoriesProduct.clear()
                self.ui.comboBoxCategoriesProduct.addItems(
                    [f'{category[0]} - {category[1]}' for category in categories])
        except Exception as e:
            print(f'Ошибка: {e}')

    def filter_product(self):
        select_category = self.ui.comboBox_categories.currentText()
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT P.name, I.url, C.name_categories, P.amount, P.price
                    FROM product P
                    JOIN image I ON P.id_image = I.id_image
                    JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    WHERE C.name_categories = %s
                    LIMIT 100;
                ''', (select_category,))
                records = cursor.fetchall()

                self.model_table_product.clear()
                self.model_table_product.setColumnCount(5)
                self.model_table_product.setHorizontalHeaderLabels(
                    ['Наименование', 'Изображение', 'категория', 'Количество', 'Цена'])
                self.horizontal_header = self.ui.tableProductOrder.horizontalHeader()

                for i in range(0, 5):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Stretch)

                for index, record in enumerate(records, start=1):
                    self.model_table_product.appendRow([])
                    for col, value in enumerate(record):
                        if col == 1:
                            pixmap = QPixmap()
                            pixmap.loadFromData(value)
                            scaled_pixmap = pixmap.scaled(QSize(150, 150), Qt.KeepAspectRatio)
                            image_label = QLabel()
                            image_label.setPixmap(scaled_pixmap)
                            image_label.setAlignment(Qt.AlignCenter)
                            self.ui.tableProductOrder.setIndexWidget(self.model_table_product.index(index - 1, col),
                                                                     image_label)
                        else:
                            item = QStandardItem(str(value))
                            self.model_table_product.setItem(index - 1, col, item)

        except Exception as e:
            print(f'Ошибка: {e}')

    def search_product(self):
        search_text = self.ui.lineEditSearch.text().strip()
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT P.name, I.url, C.name_categories, P.amount, P.price
                    FROM product P
                    JOIN image I ON P.id_image = I.id_image
                    JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    WHERE LOWER(P.name) LIKE LOWER(%s) OR LOWER(C.name_categories) LIKE LOWER(%s);
                ''', ('%' + search_text + '%', '%' + search_text + '%'))
                records = cursor.fetchall()

                self.model_table_product.clear()
                self.model_table_product.setColumnCount(5)
                self.model_table_product.setHorizontalHeaderLabels(
                    ['Наименование', 'Изображение', 'категория', 'Количество', 'Цена'])
                self.horizontal_header = self.ui.tableProductOrder.horizontalHeader()

                for i in range(0, 5):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Stretch)

                for index, record in enumerate(records, start=1):
                    self.model_table_product.appendRow([])
                    for col, value in enumerate(record):
                        if col == 1:
                            pixmap = QPixmap()
                            pixmap.loadFromData(value)
                            scaled_pixmap = pixmap.scaled(QSize(150, 150), Qt.KeepAspectRatio)
                            image_label = QLabel()
                            image_label.setPixmap(scaled_pixmap)
                            image_label.setAlignment(Qt.AlignCenter)
                            self.ui.tableProductOrder.setIndexWidget(self.model_table_product.index(index - 1, col),
                                                                     image_label)
                        else:
                            item = QStandardItem(str(value))
                            self.model_table_product.setItem(index - 1, col, item)
        except Exception as e:
            print(f'Ошибка: {e}')

    def get_data_main_product(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                        SELECT P.name, I.url, C.name_categories  || ' - ' || PC.name AS category, P.description, P.amount, P.price
                        FROM product P
                        JOIN image I ON P.id_image = I.id_image
                        JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                        JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                        JOIN categories C ON CPC.id_categories = C.id_categories;
                    ''')
                records = cursor.fetchall()

                self.model_table_main_product.clear()
                self.model_table_main_product.setColumnCount(8)
                self.model_table_main_product.setHorizontalHeaderLabels(
                    ['Наименование', 'Изображение', 'Категория', 'Описание', 'Количество', 'Цена', '', ''])
                self.horizontal_header = self.ui.tableProduct.horizontalHeader()

                for i in range(0, 6):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Stretch)

                for i in range(6, 8):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Fixed)
                    self.horizontal_header.resizeSection(i, 65)

                for index, record in enumerate(records, start=1):
                    self.model_table_main_product.appendRow([])
                    for col, value in enumerate(record):
                        if col == 1:
                            pixmap = QPixmap()
                            pixmap.loadFromData(value)
                            scaled_pixmap = pixmap.scaled(QSize(150, 150), Qt.KeepAspectRatio)
                            image_label = QLabel()
                            image_label.setPixmap(scaled_pixmap)
                            image_label.setAlignment(Qt.AlignCenter)
                            self.ui.tableProduct.setIndexWidget(self.model_table_main_product.index(index - 1, col),
                                                                image_label)
                        else:
                            item = QStandardItem(str(value))
                            self.model_table_main_product.setItem(index - 1, col, item)

                    edit_button = QPushButton(self)
                    edit_button.setFixedSize(60, 60)
                    edit_button.setIcon(QIcon(
                        QPixmap(directory + f'/icon/edit.png').scaled(QSize(60, 60))))
                    edit_button.clicked.connect(lambda _, i=index - 1: self.edit_product(i))
                    self.ui.tableProduct.setIndexWidget(self.model_table_main_product.index(index - 1, 6),
                                                        edit_button)
                    delete_button = QPushButton(self)
                    delete_button.setFixedSize(60, 60)
                    delete_button.setIcon(QIcon(QPixmap(directory + f'/icon/delete.png').scaled(QSize(60, 60))))
                    delete_button.clicked.connect(lambda _, i=index - 1: self.delete_product(i))
                    self.ui.tableProduct.setIndexWidget(self.model_table_main_product.index(index - 1, 7),
                                                        delete_button)
                    self.ui.tableProduct.verticalHeader().setDefaultSectionSize(65)
        except Exception as e:
            print(f'Ошибка: {e}')

    def get_data_product(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT P.name, I.url, C.name_categories, P.amount, P.price
                    FROM product P
                    JOIN image I ON P.id_image = I.id_image
                    JOIN categories_parent_category CPC ON P.id_category = CPC.id_categories_parent_category
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    JOIN categories C ON CPC.id_categories = C.id_categories;
                ''')
                records = cursor.fetchall()

                self.model_table_product.clear()
                self.model_table_product.setColumnCount(5)
                self.model_table_product.setHorizontalHeaderLabels(
                    ['Наименование', 'Изображение', 'Категория', 'Количество', 'Цена'])
                self.horizontal_header = self.ui.tableProductOrder.horizontalHeader()

                for i in range(0, 5):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Stretch)

                for index, record in enumerate(records, start=1):
                    self.model_table_product.appendRow([])
                    for col, value in enumerate(record):
                        if col == 1:
                            pixmap = QPixmap()
                            pixmap.loadFromData(value)
                            scaled_pixmap = pixmap.scaled(QSize(150, 150), Qt.KeepAspectRatio)
                            image_label = QLabel()
                            image_label.setPixmap(scaled_pixmap)
                            image_label.setAlignment(Qt.AlignCenter)
                            self.ui.tableProductOrder.setIndexWidget(self.model_table_product.index(index - 1, col),
                                                                     image_label)
                        else:
                            item = QStandardItem(str(value))
                            self.model_table_product.setItem(index - 1, col, item)

        except Exception as e:
            print(f'Ошибка: {e}')

    def insert_data_product(self):
        try:
            with connection.cursor() as cursor:
                name_product = self.ui.lineEditNameProduct.text()
                combo_box_product = self.ui.comboBoxCategoriesProduct.currentText()
                description_product = self.ui.textEditDescriptionProduct.toPlainText()
                amount_product = self.ui.lineEditAmountProduct.text()
                price_product = self.ui.lineEditPriceProduct.text()

                if name_product == '' or self.image_file is None or not self.image_file or description_product == '' \
                        or amount_product == '' or price_product == '':
                    show_error_message('Вы не ввели значения!')
                    return

                cursor.execute('''
                               SELECT id_product 
                               FROM product 
                               WHERE name = %s;
                           ''', (name_product,))
                existing_product = cursor.fetchone()

                if existing_product:
                    show_error_message('Продукт с таким именем уже существует!')
                    return

                with open(self.image_file, 'rb') as f:
                    image_data = f.read()

                cursor.execute('''
                    INSERT INTO image (url) 
                    VALUES (%s) 
                    RETURNING id_image;
                    ''', (psycopg2.Binary(image_data),))
                id_image = cursor.fetchone()[0]

                category_name, parent_category_name = combo_box_product.split(' - ')

                cursor.execute('''
                    SELECT CPC.id_categories_parent_category
                    FROM categories_parent_category CPC
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    WHERE C.name_categories = %s AND PC.name = %s;
                ''', (category_name, parent_category_name))

                id_categories_parent_category = cursor.fetchone()[0]

                cursor.execute('''
                    INSERT INTO product (name, id_image, id_category, description, amount, price)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_product;
                ''', (name_product, id_image, id_categories_parent_category, description_product, amount_product,
                      price_product))
            connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')

        finally:
            self.ui.lineEditNameProduct.clear()
            self.ui.textEditImageProduct.clear()
            self.ui.comboBoxCategoriesProduct.setCurrentIndex(0)
            self.ui.textEditDescriptionProduct.clear()
            self.ui.lineEditAmountProduct.clear()
            self.ui.lineEditPriceProduct.clear()
            self.filter_product()
            self.get_categories()
            self.get_data_product()
            self.get_data_main_product()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageProduct)

    def update_product(self):
        try:
            selected_row = self.ui.tableProduct.currentIndex().row()
            original_name_product = self.model_table_main_product.item(selected_row, 0).text()
            id_product = get_product_id(original_name_product)
            new_name_product = self.ui.lineEditNameProduct_2.text().strip()

            if self.image_file_2 is not None:
                with open(self.image_file_2, 'rb') as f:
                    image_data = f.read()

                with connection.cursor() as cursor:
                    cursor.execute('''
                        UPDATE image SET url = %s 
                        WHERE id_image = (SELECT id_image FROM product WHERE name = %s LIMIT 1) 
                        RETURNING id_image;
                    ''', (psycopg2.Binary(image_data), original_name_product))

                    fetch_result = cursor.fetchone()

                    if fetch_result is not None:
                        id_image = fetch_result[0]
                    else:
                        id_image = None
            else:
                id_image = None

            combo_box_product = self.ui.comboBoxCategoriesProduct_2.currentText()
            description_product = self.ui.textEditDescriptionProduct_2.toPlainText()
            amount_product = float(self.ui.lineEditAmountProduct_2.text())
            price_product = float(self.ui.lineEditPriceProduct_2.text())

            if combo_box_product == '' or description_product == '' or amount_product == '':
                show_error_message('Вы не ввели значения!')
                return

            category_name, parent_category_name = combo_box_product.split(' - ')

            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT CPC.id_categories_parent_category
                    FROM categories_parent_category CPC
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    WHERE C.name_categories = %s AND PC.name = %s;
                ''', (category_name, parent_category_name))

                id_categories_parent_category = cursor.fetchone()[0]

                cursor.execute('''
                    UPDATE product
                    SET name = %s, id_image = COALESCE(%s, id_image), id_category = %s, description = %s, amount = %s, price = %s
                    WHERE id_product = %s
                    RETURNING id_product, name;
                ''', (new_name_product, id_image, id_categories_parent_category, description_product, amount_product,
                      price_product, id_product))
            connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')

        finally:
            self.filter_product()
            self.get_data_product()
            self.get_categories()
            self.get_data_main_product()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageProduct)

    def delete_product(self, row):
        try:
            with connection.cursor() as cursor:
                product_name = self.model_table_main_product.item(row, 0).text()
                product_id = get_product_id(product_name)

                cursor.execute('''
                    SELECT id_image
                    FROM product
                    WHERE id_product = %s;
                ''', (product_id,))

                image_id = cursor.fetchone()[0]

                cursor.execute('''
                    DELETE FROM product
                    WHERE id_product = %s;
                ''', (product_id,))

                cursor.execute('''
                    DELETE FROM image
                    WHERE id_image = %s;
                ''', (image_id,))

            connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')

        finally:
            self.filter_product()
            self.get_data_product()
            self.get_categories()
            self.get_data_main_product()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageProduct)
            self.get_data_orders()

    def edit_product(self, row):
        try:
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageEditProduct)
            name_product = self.model_table_main_product.item(row, 0).text()
            description_product = self.model_table_main_product.item(row, 3).text()
            amount_product = self.model_table_main_product.item(row, 4).text()
            price_product = self.model_table_main_product.item(row, 5).text()
            category_product = self.model_table_main_product.item(row, 2).text()

            image_product = get_image_for_product(name_product)

            if image_product:
                image_base64 = base64.b64encode(image_product).decode('utf-8')
                image_html = f'<img src="data:image/png;base64,{image_base64}" width="370">'
                self.ui.textEditImageProduct_2.clear()
                self.ui.textEditImageProduct_2.setHtml(image_html)

            self.ui.textEditImageProduct_2.mousePressEvent = lambda event: self.open_image_dialog_2(event)

            self.ui.lineEditNameProduct_2.setText(name_product)
            self.ui.textEditDescriptionProduct_2.setPlainText(description_product)
            self.ui.lineEditAmountProduct_2.setText(amount_product)
            self.ui.lineEditPriceProduct_2.setText(price_product.replace('$', ''))
            self.ui.comboBoxCategoriesProduct_2.setCurrentText(category_product)

            if image_product is None:
                self.ui.textEditImageProduct_2.clear()

        except Exception as e:
            print(f'Ошибка: {e}')

    def get_categories_parent_category_2(self):
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT C.name_categories, PC.name
                FROM categories_parent_category CPC
                JOIN categories C ON CPC.id_categories = C.id_categories
                JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
            ''')
            categories = cursor.fetchall()
            category_names = [f'{name} - {parent}' for name, parent in categories]
            self.ui.comboBoxCategoriesProduct_2.clear()
            self.ui.comboBoxCategoriesProduct_2.addItems(category_names)

    def get_data_categories(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT C.name_categories, P.name
                    FROM categories_parent_category CPC
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    JOIN parent_category P ON CPC.id_parent_categories = P.id_parent_category
                    ORDER BY P.id_parent_category;
                ''')
                records = cursor.fetchall()

                self.model_table_categories.clear()
                self.model_table_categories.setColumnCount(4)
                self.model_table_categories.setHorizontalHeaderLabels(
                    ['Имя категории', 'Имя родительской категории', '', ''])
                self.horizontal_header = self.ui.tableAddCategories.horizontalHeader()

                for i in range(0, 2):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Stretch)

                for i in range(2, 4):
                    self.horizontal_header.setSectionResizeMode(i, QHeaderView.Fixed)
                    self.horizontal_header.resizeSection(i, 65)

                for index, record in enumerate(records, start=1):
                    self.model_table_categories.appendRow([])
                    for col, value in enumerate(record):
                        item = QStandardItem(str(value))
                        self.model_table_categories.setItem(index - 1, col, item)

                    edit_button = QPushButton(self)
                    edit_button.setFixedSize(60, 60)
                    edit_button.setIcon(QIcon(
                        QPixmap(directory + f'/icon/edit.png').scaled(QSize(60, 60))))
                    edit_button.clicked.connect(lambda _, i=index - 1: self.edit_categories(i))
                    self.ui.tableAddCategories.setIndexWidget(self.model_table_categories.index(index - 1, 2),
                                                              edit_button)
                    delete_button = QPushButton(self)
                    delete_button.setFixedSize(60, 60)
                    delete_button.setIcon(QIcon(QPixmap(directory + f'/icon/delete.png').scaled(QSize(60, 60))))
                    delete_button.clicked.connect(lambda _, i=index - 1: self.delete_categories(i))
                    self.ui.tableAddCategories.setIndexWidget(self.model_table_categories.index(index - 1, 3),
                                                              delete_button)
                self.ui.tableAddCategories.verticalHeader().setDefaultSectionSize(65)

        except Exception as e:
            print(f'Ошибка: {e}')

    def insert_data_categories(self):
        try:
            with connection.cursor() as cursor:
                name_categories = self.ui.lineEditNameCategory.text()
                parent_categories = self.ui.lineEditParentCategory.text()

                if name_categories == '' or parent_categories == '':
                    show_error_message('Вы не ввели значения!')
                    return

                cursor.execute('''
                    SELECT id_categories 
                    FROM categories 
                    WHERE name_categories = %s;
                ''', (name_categories,))
                existing_category = cursor.fetchone()

                if existing_category:
                    id_categories = existing_category[0]
                else:
                    cursor.execute('''
                        INSERT INTO categories (name_categories) VALUES (%s) 
                        RETURNING id_categories;
                    ''', (name_categories,))
                    result = cursor.fetchone()

                    if result:
                        id_categories = result[0]
                    else:
                        show_error_message('Ошибка при добавлении записи в категории!')
                        return
                cursor.execute('''
                    SELECT id_parent_category 
                    FROM parent_category 
                    WHERE name = %s;
                ''', (parent_categories,))
                existing_parent_category = cursor.fetchone()

                if existing_parent_category:
                    show_error_message('Такая запись уже существует!')
                    return
                cursor.execute('''
                    INSERT INTO parent_category (name) VALUES (%s) 
                    RETURNING id_parent_category;
                ''', (parent_categories,))
                result = cursor.fetchone()
                if result:
                    id_parent_category = result[0]
                else:
                    show_error_message('Ошибка при добавлении родительской категории!')
                    return

                cursor.execute('''
                    SELECT 1 
                    FROM categories_parent_category 
                    WHERE id_categories = %s AND id_parent_categories = %s;
                ''', (id_categories, id_parent_category))
                existing_relation = cursor.fetchone()

                if existing_relation:
                    show_error_message('Cвязь между категорией и родительской категорией уже существует!')
                    return

                cursor.execute('''
                    INSERT INTO categories_parent_category (id_categories, id_parent_categories) 
                    VALUES (%s, %s);
                ''', (id_categories, id_parent_category))
                connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при добавлении записи!')

        finally:
            self.ui.lineEditNameCategory.clear()
            self.ui.lineEditParentCategory.clear()
            self.get_data_categories()
            self.get_categories_parent_category()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCategories)

    def edit_categories(self, row):
        try:
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageEditCategories)
            categories_name = self.model_table_categories.item(row, 0).text()
            parent_categories_name = self.model_table_categories.item(row, 1).text()
            categories_id = get_category_id(categories_name)
            parent_categories_id = get_parent_category_id(parent_categories_name)
            self.ui.lineEditNameCategory_2.setText(categories_name)
            self.ui.lineEditParentCategory_2.setText(parent_categories_name)
            self.current_edit_categories_id = categories_id
            self.current_edit_parent_categories_id = parent_categories_id

        except Exception as e:
            print(f'Ошибка: {e}')

    def update_categories(self):
        try:
            new_categories_name = self.ui.lineEditNameCategory_2.text()
            new_parent_categories_name = self.ui.lineEditParentCategory_2.text()

            with connection.cursor() as cursor:
                if new_categories_name:
                    cursor.execute('''
                        UPDATE categories 
                        SET name_categories = %s 
                        WHERE id_categories = %s;
                    ''', (new_categories_name, self.current_edit_categories_id))
                if new_parent_categories_name:
                    cursor.execute('''
                        UPDATE parent_category 
                        SET name = %s 
                        WHERE id_parent_category = %s;
                    ''', (new_parent_categories_name, self.current_edit_parent_categories_id))
                connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при обновлении категории.')

        finally:
            self.get_categories_parent_category()
            self.get_data_categories()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCategories)

    def delete_categories(self, row):
        try:
            with connection.cursor() as cursor:
                categories_name = self.model_table_categories.item(row, 0).text()
                parent_categories_name = self.model_table_categories.item(row, 1).text()

                categories_id = get_category_id(categories_name)
                parent_categories_id = get_parent_category_id(parent_categories_name)

                cursor.execute('''
                    DELETE FROM categories_parent_category 
                    WHERE id_categories = %s AND id_parent_categories = %s;
                ''', (categories_id, parent_categories_id))

                cursor.execute('''
                    SELECT 1 
                    FROM categories_parent_category 
                    WHERE id_categories = %s;
                ''', (categories_id,))
                existing_relations = cursor.fetchall()

                if not existing_relations:
                    cursor.execute('''
                        DELETE FROM categories 
                        WHERE id_categories = %s;
                    ''', (categories_id,))

                cursor.execute('''
                    SELECT 1 
                    FROM categories_parent_category 
                    WHERE id_parent_categories = %s;
                ''', (parent_categories_id,))
                existing_relations = cursor.fetchall()

                if not existing_relations:
                    cursor.execute('''
                        DELETE FROM parent_category 
                        WHERE id_parent_category = %s;
                    ''', (parent_categories_id,))

                connection.commit()
        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при удалении записи.')

        finally:
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCategories)
            self.get_data_main_product()
            self.get_data_categories()
            self.get_categories_parent_category()
            self.get_data_product()

    def animate_menu_width(self, enable):
        width = self.ui.frameLeftMenu.width()
        maxExtend = 150
        standard = 70
        if width == 70:
            widthExtended = maxExtend
        else:
            widthExtended = standard

        if enable:
            self.animation = QPropertyAnimation(self.ui.frameLeftMenu, b'minimumWidth')
            self.animation.setDuration(400)
            self.animation.setStartValue(width)
            self.animation.setEndValue(widthExtended)
            self.animation.start()
        else:
            self.animation = QPropertyAnimation(self.ui.frameLeftMenu, b'minimumWidth')
            self.animation.setDuration(400)
            self.animation.setStartValue(width)
            self.animation.setEndValue(standard)
            self.animation.start()

    def enter_event_handler(self, event):
        self.animate_menu_width(enable=True)

    def leave_event_handler(self, event):
        self.animate_menu_width(enable=False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    apply_stylesheet(app, theme='dark_blue.xml', invert_secondary=True)
    window.show()
    sys.exit(app.exec_())
