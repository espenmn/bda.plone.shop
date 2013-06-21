from decimal import Decimal
from zope.component import getUtility
from zope.i18n import translate
from zope.i18nmessageid import MessageFactory
from plone.registry.interfaces import IRegistry
from Products.CMFCore.utils import getToolByName
from bda.plone.cart import (
    readcookie,
    extractitems,
    aggregate_cart_item_count,
    get_item_data_provider,
    get_item_stock,
    get_item_state,
    get_item_preview,
    CartDataProviderBase,
    CartItemStateBase,
)
from .interfaces import IShopSettings


_ = MessageFactory('bda.plone.shop')


class CartItemCalculator(object):

    @property
    def catalog(self):
        return getToolByName(self.context, 'portal_catalog')

    def net(self, items):
        cat = self.catalog
        net = Decimal(0)
        for uid, count, comment in items:
            brain = cat(UID=uid)
            if not brain:
                continue
            data = get_item_data_provider(brain[0].getObject())
            net += Decimal(str(data.net)) * count
        return net

    def vat(self, items):
        cat = self.catalog
        vat = Decimal(0)
        for uid, count, comment in items:
            brain = cat(UID=uid)
            if not brain:
                continue
            data = get_item_data_provider(brain[0].getObject())
            vat += (Decimal(str(data.net)) / Decimal(100)) \
                   * Decimal(str(data.vat)) * count
        return vat


class CartItemState(CartItemStateBase):

    @property
    def aggregated_count(self):
        items = extractitems(readcookie(self.request))
        return aggregate_cart_item_count(self.context.UID(), items)

    @property
    def completely_exceeded_message(self):
        message = _(u'alert_item_no_longer_available',
                    default=u'Item is no longer available, please '
                            u'remove from cart')
        return translate(message, context=self.request)

    @property
    def some_reservations_message(self):
        message = _(u'alert_item_some_reserved',
                    default=u'Some items reserved')
        return translate(message, context=self.request)

    def partly_exceeded_message(self, exceed):
        message = _(u'alert_item_number_exceed',
                    default=u'Limit exceed by ${exceed} items',
                    mapping={'exceed': exceed})
        return translate(message, context=self.request)

    def number_reservations_message(self, reserved):
        message = _(u'alert_item_number_reserved',
                    default=u'${reserved} items reserved',
                    mapping={'reserved': reserved})
        return translate(message, context=self.request)

    def message(self, count):
        stock = get_item_stock(self.context)
        available = stock.available
        overbook = stock.overbook
        # no limitation
        if available is None:
            return ''
        # read aggregated item count for cart item
        aggregated_count = float(self.aggregated_count)
        count = float(count)
        # number of reserved items
        reserved = 0.0
        if available <= 0:
            reserved = aggregated_count
        elif available - aggregated_count < 0:
            reserved = abs(available - aggregated_count)
        # number of items exceeded limit
        exceed = 0.0
        if overbook is not None:
            if reserved > overbook:
                exceed = reserved - overbook
        # no reservations and no exceed
        if not reserved and not exceed:
            # no message
            return ''
        # total number items available
        if available >= 0:
            total_available = available + overbook
        else:
            total_available = overbook - available
        # exceed
        if exceed:
            # partly exceeded
            if total_available > 0:
                return self.partly_exceeded_message(exceed)
            # completely exceeded
            return self.completely_exceeded_message
        # reservations
        if reserved:
            # some reservations message
            if aggregated_count > count:
                return self.some_reservations_message
            # number reservations message
            else:
                return self.number_reservations_message(reserved)
        return ''

    def validate_count(self, count):
        count = float(count)
        stock = get_item_stock(self.context)
        available = stock.available
        overbook = stock.overbook
        if available is None or overbook is None:
            return True
        available -= count
        if available >= overbook * -1:
            return True
        return False


class CartDataProvider(CartItemCalculator, CartDataProviderBase):

    def cart_items(self, items):
        cat = self.catalog
        ret = list()
        for uid, count, comment in items:
            brain = cat(UID=uid)
            if not brain:
                continue
            brain = brain[0]
            obj = brain.getObject()
            title = brain.Title
            data = get_item_data_provider(obj)
            price = Decimal(str(data.net)) * count
            if data.display_gross:
                price = price + price / Decimal(100) * Decimal(str(data.vat))
            url = brain.getURL()
            description = brain.Description
            comment_required = data.comment_required
            quantity_unit_float = data.quantity_unit_float
            quantity_unit = translate(data.quantity_unit, context=self.request)
            preview_image_url = get_item_preview(obj).url
            item_state = get_item_state(obj, self.request)
            no_longer_available = not item_state.validate_count(count)
            alert = item_state.message(count)
            item = self.item(
                uid, title, count, price, url, comment, description,
                comment_required, quantity_unit_float, quantity_unit,
                preview_image_url, no_longer_available, alert)
            ret.append(item)
        return ret

    @property
    def _settings(self):
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IShopSettings)
        return settings

    @property
    def currency(self):
        return self._settings.currency

    @property
    def show_checkout(self):
        return self._settings.show_checkout

    @property
    def show_to_cart(self):
        return self._settings.show_to_cart

    @property
    def show_currency(self):
        return self._settings.show_currency

    @property
    def disable_max_article(self):
        return self._settings.disable_max_article

    @property
    def summary_total_only(self):
        return self._settings.summary_total_only

    @property
    def include_shipping_costs(self):
        return self._settings.include_shipping_costs

    @property
    def shipping_method(self):
        return self._settings.shipping_method

    @property
    def checkout_url(self):
        return '%s/@@checkout' % self.context.absolute_url()
