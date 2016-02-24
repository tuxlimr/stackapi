import requests
from itertools import chain
from time import sleep

try:
    import json
except ImportError:
    import simplejson as json


class StackAPIError(Exception):
    """
    The Exception that is thrown when ever there is an API error.
    
    This utilizes the values returned by the API and described
    here: http://api.stackexchange.com/docs/types/error
    
    Parameters
    ----------
    
        url : string
            The URL that was called and generated an error
        error : int
            The `error_id` returned by the API (should be an int)
        code : string
            The `description` returned by the API and is human friendly
        message : string
            The `error_name` returned by the API
    """

    def __init__(self, url, error, code, message):
        self.url = url
        self.error = error
        self.code = code
        self.message = message


class StackAPI(object):
    def __init__(self, name=None, version="2.2", **kwargs):
        """
        The object used to interact with the Stack Exchange API
        
        Attributes
        ----------
        
        name : string
            (Required): A valid `api_site_parameter` 
            (avaiable from http://api.stackexchange.com/docs/sites) which will
            be used to connect to a particular site on the Stack Exchange
            Network.
        version : float
            (Required) The version of the API you are connecting to. The 
            default of 2.2 is the current version
        kwargs : {proxy, max_pages, page_size, key, access_token}
            proxy - A dictionary of http and https proxy locations
                Example: {'http': 'http://example.com', 
                          'https': 'https:example.com'}
                By default, this is `None`.
            max_pages - The maximium number of pages to retreive (Default: 100)
            page_size - The number of elements per page. The API limits this to
                a maximum of 100 items on all end points except `site`
            key - An API key 
            access_token - An access token associated with an application and 
                a user, to grant more permissions (such as write access)
   
        """
        if not name:
            raise ValueError('No Site Name provided')

        self.proxy = kwargs['proxy'] if kwargs.get('proxy') else None
        self.max_pages = kwargs['max_pages'] if kwargs.get('max_pages') else 100
        self.page_size = kwargs['page_size'] if kwargs.get('page_size') else 100
        self.key = kwargs['key'] if kwargs.get('key') else None
        self.access_token = kwargs['access_token'] if kwargs.get('access_token') else None
        self._endpoint = None
        self._api_key = None
        self._name = None
        self._version = version
        self._previous_call = None

        self._base_url = 'https://api.stackexchange.com/{}/'.format(version)
        sites = self.fetch('sites', filter='!*L1*AY-85YllAr2)')
        for s in sites['items']:
            if name == s['api_site_parameter']:
                self._name = s['name']
                self._api_key = s['api_site_parameter']
                break

        if not self._name:
            raise ValueError('Invalid Site Name provided')

    def __repr__(self):
        return "<{}> v:<{}> endpoint: {}  Last URL: {}".format(self._name, 
                                                               self._version, 
                                                               self._endpoint, 
                                                               self._previous_call)

    def fetch(self, endpoint=None, page=1, key=None, filter='default', **kwargs):
        """Returns the results of an API call.
        
        This is the main work horse of the class. It builds the API query 
        string and sends the request to Stack Exchange. If there are multiple 
        pages of results, and we've configured `max_pages` to be greater than 
        1, it will automatically paginate through the results and return a 
        single object.
        
        Returned data will appear in the `items` key of the resulting 
        dictionary.
        
        Parameters
        ----------
        
        endpoint : string
            The API end point being called. Available endpoints are listed on 
            the official API documentation: http://api.stackexchange.com/docs
            
            This can be as simple as `fetch('answers')`, to call the answers 
            end point
            
            If calling an end point that takes additional parameter, such as `id`s
            pass the ids as a list to the `ids` key: 
                
                `fetch('answers/{}', ids=[1,2,3])`
                
            This will attempt to retrieve the answers for the three listed ids.
            
            If no end point is passed, a `ValueError` will be raised
        page : int
            The page in the results to start at. By default, it will start on
            the first page and automatically paginate until the result set
            reached `max_pages`.
        key : string
            The site you are issuing queries to. 
        filter : string
            The filter to utilize when calling an endpoint. Different filters
            will return different keys. The default is `default` and this will
            still vary depending on what the API returns as default for a 
            particular endpoint
        kwargs :
            Parameters accepted by individual endpoints. These parameters 
            *must* be named the same as described in the endpoint documentation
            
        Returns
        -------
        
        result : dictionary
            A dictionary containing wrapper data regarding the API call
            and the results of the call in the `items` key. If multiple
            pages were retreived, all of the results will appear in the
            `items` tag.
        
        """
        if not endpoint:
            raise ValueError('No end point provided.')

        self._endpoint = endpoint
            
        params = {
            "pagesize": self.page_size,
            "page": page,
            "filter": filter
        }

        if self.key:
            params['key'] = self.key
        if self.access_token:
            params['access_token'] = self.access_token

        ids = None
        if 'ids' in kwargs:
            ids = ';'.join(str(x) for x in kwargs['ids'])
            kwargs.pop('ids', None)

        params.update(kwargs)
        if self._api_key:
            params['site'] = self._api_key

        data = []
        run_cnt = 0
        backoff = 0
        total = 0
        while run_cnt <= self.max_pages:
            run_cnt += 1

            base_url = "{}{}/".format(self._base_url, endpoint)
            if ids:
                base_url += "{}".format(ids)

            try:
                response = requests.get(base_url, params=params, proxies=self.proxy)
            except requests.exceptions.ConnectionError as e:
                raise StackAPIError(self._previous_call, str(e), str(e), str(e))

            self._previous_call = response.url
            try:
                response.encoding = 'utf-8-sig'
                response = response.json()
            except ValueError as e:
                raise StackAPIError(self._previous_call, str(e), str(e), str(e))

            try:
                error = response["error_id"]
                code = response["error_name"]
                message = response["error_message"]
                raise StackAPIError(self._previous_call, error, code, message)
            except KeyError:
                pass  # This means there is no error

            if key:
                data.append(response[key])
            else:
                data.append(response)

            if len(data) < 1:
                break

            backoff = 0
            total = 0
            page = 1
            if 'backoff' in response:
                backoff = int(response['backoff'])
                sleep(backoff+1)        # Sleep an extra second to ensure no timing issues
            if 'total' in response:
                total = response['total']
            if 'has_more' in response and response['has_more']:
                params["page"] += 1
            else:
                break


        r = []
        for d in data:
            r.extend(d['items'])
        result = {'backoff': backoff,
                  'has_more': data[-1]['has_more'],
                  'page': params['page'],
                  'quota_max': data[-1]['quota_max'],
                  'quota_remaining': data[-1]['quota_remaining'],
                  'total': total,
                  'items': list(chain(r))}

        return result

    def send_data(self, endpoint=None, page=1, key=None, filter='default', **kwargs):
        """Sends data to the API.
        
        This call is similar to `fetch`, but *sends* data to the API instead 
        of retrieving it. 
                
        Returned data will appear in the `items` key of the resulting 
        dictionary.
        
        Sending data requires that the `access_token` is set. This is enforced
        on the API side, not within this library.
        
        Parameters
        ----------
        
        endpoint : string
            The API end point being called. Available endpoints are listed on 
            the official API documentation: http://api.stackexchange.com/docs
            
            This can be as simple as `fetch('answers')`, to call the answers 
            end point
            
            If calling an end point that takes additional parameter, such as `id`s
            pass the ids as a list to the `ids` key: 
                
                `fetch('answers/{}', ids=[1,2,3])`
                
            This will attempt to retrieve the answers for the three listed ids.
            
            If no end point is passed, a `ValueError` will be raised
        page : int
            The page in the results to start at. By default, it will start on
            the first page and automatically paginate until the result set
            reached `max_pages`.
        key : string
            An API key
        filter : string
            The filter to utilize when calling an endpoint. Different filters
            will return different keys. The default is `default` and this will
            still vary depending on what the API returns as default for a 
            particular endpoint
        kwargs :
            Parameters accepted by individual endpoints. These parameters 
            *must* be named the same as described in the endpoint documentation
            
        Returns
        -------
        
        result : dictionary
            A dictionary containing wrapper data regarding the API call
            and the results of the call in the `items` key. If multiple
            pages were retreived, all of the results will appear in the
            `items` tag.
        
        """
        if not endpoint:
            raise ValueError('No end point provided.')

        self._endpoint = endpoint

        params = {
            "pagesize": self.page_size,
            "page": page,
            "filter": filter
        }

        if self.key:
            params['key'] = self.key
        if self.access_token:
            params['access_token'] = self.access_token

        if 'ids' in kwargs:
            ids = ';'.join(str(x) for x in kwargs['ids'])
            kwargs.pop('ids', None)
        else:
            ids = None

        params.update(kwargs)
        if self._api_key:
            params['site'] = self._api_key

        data = []

        base_url = "{}{}/".format(self._base_url, endpoint)
        response = requests.post(base_url, data=params, proxies=self.proxy)
        self._previous_call = response.url
        response = response.json()

        try:
            error = response["error_id"]
            code = response["error_name"]
            message = response["error_message"]
            raise StackAPIError(self._previous_call, error, code, message)
        except KeyError:
            pass  # This means there is no error

        data.append(response)
        r = []
        for d in data:
            r.extend(d['items'])
        result = {'has_more': data[-1]['has_more'],
                  'page': params['page'],
                  'quota_max': data[-1]['quota_max'],
                  'quota_remaining': data[-1]['quota_remaining'],
                  'items': list(chain(r))}

        return result