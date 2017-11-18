from bs4 import BeautifulSoup
from contextlib import suppress
import pandas as pd
import requests
import json
import re



class RightMoveAPI():
    """store dataframe of rightmove search results"""
    user_agent = "Python_House_Hunting"
    base_url = "http://www.rightmove.co.uk/property-for-sale/find.html?"
    rightmove = "http://www.rightmove.co.uk"
    default_outcode = "LS26"  # Rothwell, Leeds
    property_links = []
    total_pages = None
    search_url = None


    def __init__(self, *args, **kwargs):
        """initialisation"""
        self.loc_linking = self._import_json()
        self.results = pd.DataFrame(columns=["Price", "Beds", "Location", "Description"])
        
    def _import_json(self):
        """opens json linking table and converts to json object"""
        with open("RightMove-outcodes.json", "r") as f:
            raw_json = f.read()
        return json.loads(raw_json)

    def _extract_location_code(self, outcode):
        """Looks up outcode in RightMove lookup json"""
        for c in self.loc_linking:
            outcode_match = c["outcode"]
            if outcode == outcode_match:
                return c["code"]
            else:
                continue
        return False

    def _construct_search_url(self, **kwargs):
        """Process user search terms"""

        def _locationIdentifier(outcode):
            """returns search term to be used for location"""
            if not outcode: return False
            code = self._extract_location_code(outcode)
            return "locationIdentifier=OUTCODE%5E{}".format(code)

        def _radius(value):
            """returns radius search term"""
            if not value: return False
            return "radius={}".format(value)

        def _propertyTypes(values):
            """returns property type search term, including specifics"""
            # detached%2Csemi-detached%2Cterraced%2Cflat%2Cbungalow%2Cland%2Cpark-home
            if not values: return False
            return "propertyTypes={}".format("%2C".join(values))

        def _maxPrice(value):
            """returns max price search term"""
            if not value: return False
            return "maxPrice={}".format(value)

        def _minBedrooms(value):
            """returns min bedrooms search term"""
            if not value: return False
            return "minBedrooms={}".format(value)

        def _exclude(values):
            """returns exclusions search terms"""
            # newHome%2CsharedOwnership%2Cretirement
            if not values: return False
            return "dontShow={}".format("%2C".join(values))

        def _include(values):
            """returns inclusions search terms"""
            # garden%2Cparking%2CnewHome%2Cretirement%2CsharedOwnership%2Cauction
            if not values: return False
            return "mustHave={}".format("%2C".join(values))
        
        def _sstc(bool):
            """return sstc is true or false term"""
            if not bool: return False
            return "includeSSTC={}".format(bool)
     
        def _maxDays(value):
            """returns days since put on market term"""
            # 1,3,7 or 14 only
            if not value or value not in [1,3,7,14]: return False
            return "maxDaysSinceAdded={}".format(value)
 
        search_terms = [_locationIdentifier(kwargs.get("location", self.default_outcode)),
                        _radius(kwargs.get("radius", False)),
                        _propertyTypes(kwargs.get("type", False)),
                        _maxPrice(kwargs.get("max_price", False)),
                        _minBedrooms(kwargs.get("min_bedrooms", False)),
                        _exclude(kwargs.get("exclusions", False)),
                        _include(kwargs.get("inclusions", False)),
                        _sstc(kwargs.get("sstc", False)),
                        _maxDays(kwargs.get("maxdays", False))]

        self.search_url = self.base_url + "&".join([t for t in search_terms if t])
        return self.search_url


    def _init_soup(self, content):
        """Initialise Beautiful Soup object"""
        soup = BeautifulSoup(content, "html.parser")  # "lxml"
        return soup


    def _get_page_content(self, href):
        """Use Requests to return contents of web page"""
        result = requests.get(href, headers={'User-Agent': self.user_agent})
        status_code = result.status_code
        if status_code == 200:
            content = result.content
            return self._init_soup(content)
        else:
            print("Failed to get page: {}".format(href))
            return False


    def _extract_totalpages(self, soup):
        """Extracts page total so loop can stop at correct point"""
        pattern = re.compile(r"\"pagination\":{\"total\":([0-9]+)")
        script = soup.find("script", text=pattern)
        total_pages = int(pattern.search(script.text).group(1))
        self.total_pages = total_pages
        return self.total_pages


    def _parse_list_of_results(self, soup):
        """Parse list of result links"""
        div_tags = soup.findAll("div", { "class" : "propertyCard-details" })
        for tags in div_tags:
            a = tags.find("a", { "class" : "propertyCard-link" })
            href = "{}{}".format(self.rightmove, a['href'])
            if not href.endswith("html") or href.endswith("/property-0.html"):
                continue
            else:
                if href not in self.property_links:
                    self.property_links.append(href)
        return 

    def _add_page_to_search_url(self, url, page_num):
        """Appends the index search term to the url with the correct page value"""
        index = (page_num - 1) * 24
        index_str = "index={}".format(index)
        return "{}&{}".format(url, index_str)

  
    def _parse_house_details(self, soup):
        """Extract data about the property"""

        def _extract_price(soup):
            """Use RegEx to extract price from £000,000,000"""
            recomp = re.compile(r"£([0-9]{0,3}),?([0-9]{0,3}),?([0-9]{0,3})")
            p_tag = soup.find(id="propertyHeaderPrice").find("strong")
            return int("".join(re.findall(recomp, p_tag.contents[0])[0]))

        def _extract_beds(soup):
            """Extract number from beginning of title indicating number of beds."""
            h1_tag = soup.find("h1", {"class": "fs-22", "itemprop": "name"})
            return int((h1_tag.contents[0]).split()[0])

        def _extract_address(soup):
            """Extract address from a meta tag."""
            meta_tag = soup.find("meta", {"itemprop": "streetAddress"})
            return meta_tag["content"]

        def _extract_description(soup):
            """Extract description contents as a block of text"""
            p_tag = soup.find("p", {"itemprop": "description"})
            return (p_tag.get_text()
                         .strip("\n")
                         .strip("\xa0")
                         .strip("\r\n")
                         .strip("\r"))

        details = (_extract_price(soup),
                   _extract_beds(soup),
                   _extract_address(soup),
                   _extract_description(soup))

        return details


    def _append_to_df(self, house_details):
        """Adds new row in master df with house details"""
        self.results.loc[len(self.results)] = house_details

    def Search(self, **kwargs):
        """input: search terms; output: df of house details"""
        self.search_url = self._construct_search_url(**kwargs)
        #print(self.search_url)
        soup = self._get_page_content(self.search_url)
        self._parse_list_of_results(soup)
        self.total_pages = self._extract_totalpages(soup)
        #print("Total pages: {}".format(self.total_pages))
        for page_number in range(2,self.total_pages+1):
            #print("Properties found: {}".format(len(self.property_links)))
            new_search_url = self._add_page_to_search_url(self.search_url, page_number)
            #print("Search URL: {}".format(new_search_url))
            soup = self._get_page_content(new_search_url)
            if soup:
                self._parse_list_of_results(soup)
            else:
                break
        for property in self.property_links:
            soup = self._get_page_content(property)
            try:
                house_details = self._parse_house_details(soup)
                self.results.loc[len(self.results)] = house_details
            except AttributeError:
                print(property)

        return self.results







           





test = RightMoveAPI()
#soup = test._get_page_content("http://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=OUTCODE%5E1543&minBedrooms=2&maxPrice=150000&radius=20.0&propertyTypes=bungalow%2Cdetached%2Csemi-detached%2Cterraced&maxDaysSinceAdded=14&mustHave=garden&dontShow=sharedOwnership%2Cretirement")
#print(test._construct_search_url(radius=20, max_price=150000, maxdays=14, min_bedrooms=2, 
                                # inclusions=['garden'], 
                               #  type=['detached', 'semi-detached', 'terraced', 'bungalow'], 
                               #  exclusions=['sharedOwnership', 'retirement'] ))

#print(test._extract_totalpages(soup))


#//*[@id="l-container"]/div[3]/div/div/div/div[2]/span[3]
# <span class="pagination-pageInfo" data-bind="text: total">42</span>
#with open("C:\\Users\\Rich\\Desktop\\content.txt", "w") as f: f.write(str(script_tags))

#prop = "http://www.rightmove.co.uk/property-for-sale/property-68487332.html"
#soup = test._get_page_content(prop)
#prop_description = test._parse_house_details(soup)
#print(prop_description)

results = test.Search(radius=0, max_price=150000)
print(results)


# TODO
# Include url in output dataframe
# upload to github
# create test environment
# create simple documentation
