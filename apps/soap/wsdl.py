from spyne import Application
from spyne.protocol.soap import Soap11
from spyne.server.django import DjangoApplication
from .services import UFAAWebService

# WSDL definition
soap_app = Application(
    [UFAAWebService],
    tns='urn:ufaa:wsdl',
    in_protocol=Soap11(validator='lxml'),
    out_protocol=Soap11()
)

# WSDL will be automatically generated at /soap/wsdl/