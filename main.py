import os
import sys
from functools import partial
from PyQt5.QtCore import QPropertyAnimation, QSize, QRegExp
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QPixmap, QRegExpValidator
from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QPushButton, QHeaderView

from database import connection
from ui_main import Ui_MainWindow
from qt_material import apply_stylesheet

directory = os.path.abspath(os.curdir)
russian_validator = QRegExpValidator(QRegExp('[А-Яа-яЁё ]+'))
real = QRegExpValidator(QRegExp('^[0-9]+(\.[0-9]{1,2})?$'))
integer = QRegExpValidator(QRegExp('^[0-9]+$'))


# dictionary = {1: 'Сухой корм вкус курицы',
#               2: 'Сухой корм вкус индейки',
#               3: 'Жидкий корм вкус рыбы',
#               4: 'Жидкий корм вкус томата',
#               5: 'Игрушка с ароматизатором курицы',
#               6: 'Игрушка с ароматизатором мяты',
#               7: 'Игрушка в виде серой мыши',
#               8: 'Игрушка в виде воробья',
#               9: 'Крупный древесный наполнитель',
#               10: 'Мелкий древесный наполнитель'}


def show_error_message(message):
    msg = QMessageBox()
    msg.setWindowIcon(QIcon(directory + f'/icon/danger.png'))
    msg.setIcon(QMessageBox.Warning)
    msg.setStyleSheet('background-color: rgb(94, 94, 94)')
    msg.setText(message)
    msg.setWindowTitle("Сообщение об ошибке")
    msg.exec_()


def get_category_id(categories_name):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id_categories FROM categories WHERE name_categories = %s;', (categories_name,))
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
            cursor.execute('SELECT id_parent_category FROM parent_category WHERE name = %s;', (parent_category_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                return None
    except Exception as e:
        print(f'Ошибка: {e}')
        return None


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.current_edit_parent_categories_id = None
        self.current_edit_categories_id = None
        self.vertical_header = None
        self.horizontal_header = None
        self.header = None
        self.animation = None

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.Widget_pages.setCurrentWidget(self.ui.pageCatalog)

        self.ui.frameLeftMenu.enterEvent = self.enter_event_handler
        self.ui.frameLeftMenu.leaveEvent = self.leave_event_handler

        self.ui.catalog.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCatalog))
        self.ui.products.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageAddProduct))
        self.ui.orders.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageOrderList))
        self.ui.reports.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageReports))
        self.ui.categories.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCategories))
        self.ui.addCategoriesList.clicked.connect(
            partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageAddCategories))
        self.ui.cancelCategories.clicked.connect(
            partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCategories))
        self.ui.addCategories.clicked.connect(self.insert_data_categories)
        self.ui.applyEditCategories.clicked.connect(self.update_categories)
        self.ui.addProduct.clicked.connect(self.insert_data_product)
        self.ui.cancelEditCategories.clicked.connect(
            partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCategories))
        self.ui.cancelProduct.clicked.connect(partial(self.ui.Widget_pages.setCurrentWidget, self.ui.pageCatalog))

        # data_list = [f'{key}: {value}' for key, value in dictionary.items()]
        # self.model_table_catalog_product = QStandardItemModel(data_list)
        # self.ui.tableCatalogProduct.setModel(self.model_table_catalog_product)

        self.ui.comboBoxCategoriesProduct.currentIndexChanged.connect(self.get_data_categories_parent_category)
        self.model_table_categories = QStandardItemModel()
        self.ui.tableAddCategories.setModel(self.model_table_categories)
        self.get_data_categories()
        self.get_data_categories_parent_category()

        self.ui.lineEditNameCategory.setValidator(russian_validator)
        self.ui.lineEditParentCategory.setValidator(russian_validator)
        self.ui.lineEditParentCategory_2.setValidator(russian_validator)
        self.ui.lineEditNameCategory_2.setValidator(russian_validator)
        self.ui.lineEditNameProduct.setValidator(russian_validator)

        self.ui.lineEditAmountProduct.setValidator(integer)
        self.ui.lineEditPriceProduct.setValidator(real)

    def get_data_categories_parent_category(self):
        try:
            self.ui.comboBoxCategoriesProduct.currentIndexChanged.disconnect(self.get_data_categories_parent_category)
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT C.name_categories, PC.name
                    FROM categories_parent_category CPC
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    ORDER BY C.name_categories;
                ''')
                categories = cursor.fetchall()

                self.ui.comboBoxCategoriesProduct.addItems(
                    [f'{category[0]} - {category[1]}' for category in categories])
        except Exception as e:
            print(f'Ошибка: {e}')

    def insert_data_product(self):
        try:
            with connection.cursor() as cursor:
                name_product = self.ui.lineEditNameProduct.text()
                image_product_text = self.ui.textEditImageProduct.toPlainText()
                combo_box_product = self.ui.comboBoxCategoriesProduct.currentText()
                description_product = self.ui.textEditDescriptionProduct.toPlainText()
                amount_product = int(self.ui.lineEditAmountProduct.text())
                price_product = int(self.ui.lineEditPriceProduct.text())

                if name_product == '' or image_product_text == '' or combo_box_product == '' or description_product == '' \
                        or amount_product == '' or price_product == '':
                    show_error_message('Вы не ввели значения!')
                    return

                category_name, parent_category_name = combo_box_product.split(' - ')

                cursor.execute('''
                    SELECT CPC.id_categories_parent_category
                    FROM categories_parent_category CPC
                    JOIN categories C ON CPC.id_categories = C.id_categories
                    JOIN parent_category PC ON CPC.id_parent_categories = PC.id_parent_category
                    WHERE C.name_categories = %s AND PC.name = %s;
                ''', (category_name, parent_category_name))

                id_categories_parent_category = cursor.fetchone()

                cursor.execute('INSERT INTO image (url) VALUES (%s) RETURNING id_image;', (image_product_text,))
                id_image = cursor.fetchone()

                cursor.execute(
                    'INSERT INTO product (name, id_image, id_category, description, amount, price) '
                    'VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_product;',
                    (name_product, id_image, id_categories_parent_category, description_product, amount_product,
                     price_product)
                )
            connection.commit()
        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при добавлении товара!')

        finally:
            self.ui.lineEditNameProduct.clear()
            self.ui.textEditImageProduct.clear()
            self.ui.comboBoxCategoriesProduct.setCurrentIndex(0)
            self.ui.textEditDescriptionProduct.clear()
            self.ui.lineEditAmountProduct.clear()
            self.ui.lineEditPriceProduct.clear()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCatalog)

    def insert_data_categories(self):
        try:
            with connection.cursor() as cursor:
                name_categories = self.ui.lineEditNameCategory.text()
                parent_categories = self.ui.lineEditParentCategory.text()

                if name_categories == '' or parent_categories == '':
                    show_error_message('Вы не ввели значения!')
                    return

                cursor.execute('SELECT id_categories FROM categories WHERE name_categories = %s;', (name_categories,))
                existing_category = cursor.fetchone()

                if existing_category:
                    id_categories = existing_category[0]
                else:
                    cursor.execute('INSERT INTO categories (name_categories) VALUES (%s) RETURNING id_categories;',
                                   (name_categories,))
                    result = cursor.fetchone()
                    if result:
                        id_categories = result[0]
                    else:
                        show_error_message('Ошибка при добавлении записи в категории!')
                        return

                cursor.execute('SELECT id_parent_category FROM parent_category WHERE name = %s;', (parent_categories,))
                existing_parent_category = cursor.fetchone()

                if existing_parent_category:
                    show_error_message('Такая запись уже существует!')
                    return

                cursor.execute('INSERT INTO parent_category (name) VALUES (%s) RETURNING id_parent_category;',
                               (parent_categories,))
                result = cursor.fetchone()
                if result:
                    id_parent_category = result[0]
                else:
                    show_error_message('Ошибка при добавлении родительской категории!')
                    return

                cursor.execute(
                    'SELECT 1 FROM categories_parent_category WHERE id_categories = %s AND id_parent_categories = %s;',
                    (id_categories, id_parent_category))
                existing_relation = cursor.fetchone()

                if existing_relation:
                    show_error_message('Такая связь между категорией и родительской категорией уже существует!')
                    return

                cursor.execute(
                    'INSERT INTO categories_parent_category (id_categories, id_parent_categories) VALUES (%s, %s);',
                    (id_categories, id_parent_category))
                connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при добавлении записи.')

        finally:
            self.ui.lineEditNameCategory.clear()
            self.ui.lineEditParentCategory.clear()
            self.get_data_categories()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCategories)

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
                    cursor.execute('UPDATE categories SET name_categories = %s WHERE id_categories = %s;',
                                   (new_categories_name, self.current_edit_categories_id))
                if new_parent_categories_name:
                    cursor.execute('UPDATE parent_category SET name = %s WHERE id_parent_category = %s;',
                                   (new_parent_categories_name, self.current_edit_parent_categories_id))
                connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при обновлении категории.')

        finally:
            self.get_data_categories()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCategories)

    def delete_categories(self, row):
        try:
            with connection.cursor() as cursor:
                categories_name = self.model_table_categories.item(row, 0).text()
                parent_categories_name = self.model_table_categories.item(row, 1).text()

                categories_id = get_category_id(categories_name)
                parent_categories_id = get_parent_category_id(parent_categories_name)

                cursor.execute(
                    'DELETE FROM categories_parent_category WHERE id_categories = %s AND id_parent_categories = %s;',
                    (categories_id, parent_categories_id))

                cursor.execute('SELECT 1 FROM categories_parent_category WHERE id_categories = %s;', (categories_id,))
                existing_relations = cursor.fetchall()

                if not existing_relations:
                    cursor.execute('DELETE FROM categories WHERE id_categories = %s;', (categories_id,))

                cursor.execute('SELECT 1 FROM categories_parent_category WHERE id_parent_categories = %s;',
                               (parent_categories_id,))
                existing_relations = cursor.fetchall()

                if not existing_relations:
                    cursor.execute('DELETE FROM parent_category WHERE id_parent_category = %s;',
                                   (parent_categories_id,))

                connection.commit()

        except Exception as e:
            print(f'Ошибка: {e}')
            show_error_message('Ошибка при удалении записи.')

        finally:
            self.get_data_categories()
            self.ui.Widget_pages.setCurrentWidget(self.ui.pageCategories)

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
    apply_stylesheet(app, theme='dark_yellow.xml', invert_secondary=True)
    window.show()
    sys.exit(app.exec_())
