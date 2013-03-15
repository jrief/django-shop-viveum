import httplib2
from pyquery.pyquery import PyQuery


def what_is_my_ip():
    """
    Return the remote IP address as seen by the outside world.
    This function uses a service as found here: http://findwhatismyipaddress.org/
    Run ```python utils.py``` to test this service.
    """
    conn = httplib2.Http()
    httpresp, content = conn.request('http://findwhatismyipaddress.org/', method='GET')
    assert(httpresp.status == 200)
    dom = PyQuery(content)
    elements = dom('#ipadd_n')
    assert(elements)
    td = elements('td')
    assert(td and len(td) >= 2)
    return td[1].text


if __name__ == "__main__":
    print 'My IP address is: %s' % what_is_my_ip()
