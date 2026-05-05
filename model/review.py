import os
import re
import json

import pandas as pd
from bs4 import BeautifulSoup
from zenrows import ZenRowsClient
from urllib.parse import quote, unquote

class Review:
    def __init__(
            self, 
            userID: str=None, userName: str=None, isElite: bool=None, isFirstReview: bool=None, 
            isUpdated: bool=None, shortAddress: str=None, passport: list=None, recognition: str=None, 
            rating: int=None, reviewDate: str=None, reviewComment: str=None, 
            photoNums: int=None, reactions: list=None, isPreviousReview: bool=None, 
            ownerReplyDate: str=None, ownerComment: str=None, pageNum:int=None
        ):
        self.userID = userID
        self.userName = userName
        self.isElite = isElite
        self.isFirstReview = isFirstReview
        self.isUpdated = isUpdated
        self.shortAddress = shortAddress
        self.passport = passport
        self.recognition = recognition
        self.rating = rating
        self.reviewDate = reviewDate
        self.reviewComment = reviewComment
        self.photoNums = photoNums
        self.reactions = reactions
        self.isPreviousReview = isPreviousReview
        self.ownerReplyDate = ownerReplyDate
        self.ownerComment = ownerComment
        self.pageNum = pageNum
    
    def setUserID(self, newUserid):
        self.userID = newUserid
    
    def setUserName(self, newUserName):
        self.userName = newUserName

    def setElite(self, newElite):
        self.isElite = newElite
    
    def setFirstReview(self, newFirstReview):
        self.isFirstReview = newFirstReview
    
    def setUpdated(self, newUpdated):
        self.isUpdated = newUpdated
    
    def setShortAddress(self, newShortAddress):
        self.shortAddress = newShortAddress
        
    def setPassport(self, newPassport):
        self.passport = newPassport
        
    def setRecognition(self, newRecognition):
        self.recognition = newRecognition
        
    def setRating(self, newRating):
        self.rating = newRating
    
    def setReviewDate(self, newReviewDate):
        self.reviewDate = newReviewDate
        
    def setReviewComment(self, newReviewComment):
        self.reviewComment = newReviewComment

    def setPhotoNums(self, newPhotoNums):
        self.photoNums = newPhotoNums
    
    def setReactions(self, newReactions):
        self.reactions = newReactions
    
    def setPreviousReview(self, newPreviousReview):
        self.isPreviousReview = newPreviousReview

    def setOwnerReplyDate(self, newOwnerReplyDate):
        self.ownerReplyDate = newOwnerReplyDate
    
    def setOwnerComment(self, newOwnerComment):
        self.ownerComment = newOwnerComment
    
    def setPageNum(self, newPageNum):
        self.pageNum = newPageNum
        
    def __str__(self):
        return f"""
        --------------------------
        User ID: {self.userID}
        User Name: {self.userName}
        is Elite?: {self.isElite}
        is First Reivew?: {self.isFirstReview}
        is Updated?: {self.isUpdated}
        User Short Address: {self.shortAddress}
        User Passport: {self.passport}
        User Recognition: {self.recognition}
        Rating: {self.rating}
        Date: {self.reviewDate}
        Content: {self.reviewComment}
        Number of Photos: {self.photoNums}
        Reaction to Reviews: {self.reactions}
        is Previous Reivew?: {self.isPreviousReview}
        Owner Reply Date: {self.ownerReplyDate}
        Owner Comments: {self.ownerComment}
        Page Number: {self.pageNum}
        --------------------------
        """

class Restaurant:
    restaurntNum = 0
    def __init__(self, yelpID: str, yelpName:str):
        self.yelpID = yelpID
        self.yelpName = yelpName
        self.reviewList = []
        self.restaurntNum += 1
        
    def initResFromDF(self, df: pd.DataFrame):
        for _, review in df.iterrows():
            thisReview = Review()
            thisReview.setUserID(review['userid'])
            thisReview.setElite(review['user_elite'])
            thisReview.setFirstReview(review['user_first_review'])
            thisReview.setShortAddress(review['user_loc'])
            thisReview.setPassport({'Friends': review['user_friends'], 'Reviews': review['user_reviews'], 'Photos': review['user_photos']})
            thisReview.setRecognition(review['recognition'])
            thisReview.setReviewComment(review['review'])
            thisReview.setReviewDate(review['rating_date'])
            thisReview.setRating(review['rating'])
            thisReview.setPhotoNums(review['photos'])
            thisReview.setUpdated(review['updated'])
            thisReview.setReactions({'Helpful': review['helpful'], 'Thanks': review['thanks'], 'Love this': review['love_this'], 'Oh no': review['oh_no']})
            thisReview.setOwnerReplyDate(review['owner_reply_date'])
            thisReview.setOwnerComment(review['owner_reply'])
            thisReview.setPreviousReview(review['is_previous_review'])
            if 'page_num' in df.columns:
                thisReview.setPageNum(review['page_num'])
            self.reviewList.append(thisReview)
            
    def getYelpID(self):
        return self.yelpID

    def addReview(self, newReview: Review):
        self.reviewList.append(newReview)

    def getNumReviews(self) -> int:
        return len(self.reviewList)
    
    def toDataFrame(self):
        columnNames = [
            'userid',
            'yelpid',
            'establishment',
            'user_elite',
            'user_first_review',
            'user_loc',
            'user_friends',
            'user_reviews',
            'user_photos',
            'recognition',
            'review',
            'rating',
            'rating_date',
            'updated',
            'photos',
            'helpful',
            'thanks',
            'love_this',
            'oh_no',
            'owner_reply_date',
            'owner_reply',
            'is_previous_review',
            'page_num'
        ]
        totDataList = []
        if self.getNumReviews() > 0:
            for review in self.reviewList:
                dataList = []
                dataList.append(review.userID)
                dataList.append(self.yelpID)
                dataList.append(self.yelpName)
                dataList.append(review.isElite)
                dataList.append(review.isFirstReview)
                dataList.append(review.shortAddress)
                dataList.append(review.passport['Friends'] if len(review.passport) > 0 else None)
                dataList.append(review.passport['Reviews'] if len(review.passport) > 0 else None)
                dataList.append(review.passport['Photos'] if len(review.passport) > 0 else None)
                dataList.append(review.recognition) # 추가
                dataList.append(review.reviewComment)
                dataList.append(review.rating)
                dataList.append(review.reviewDate)
                dataList.append(review.isUpdated)
                dataList.append(review.photoNums)
                dataList.append(review.reactions['Helpful'] if len(review.reactions) > 0 else None)
                dataList.append(review.reactions['Thanks'] if len(review.reactions) > 0 else None)
                dataList.append(review.reactions['Love this'] if len(review.reactions) > 0 else None)
                dataList.append(review.reactions['Oh no'] if len(review.reactions) > 0 else None)
                dataList.append(review.ownerReplyDate)
                dataList.append(review.ownerComment)
                dataList.append(review.isPreviousReview) #추가
                dataList.append(review.pageNum)
                totDataList.append(dataList)
        outputDF = pd.DataFrame(totDataList, columns=columnNames).sort_values(by=['page_num', 'rating_date', 'userid'])
        return outputDF
class InvalidElementError(Exception):
    def __init__(self, elementName):
        super().__init__(f'Invalid {elementName}')

class YelpHTML:
    callNum = 0
    # Constructor
    # URL과 API Key를 받아 ZenRows API로부터 Parsed HTML를 받음.
    # 접속에 실패한 경우가 아니라면, Scraping에 필요한 Element들이 제대로 포함되어 있는지 검증.
    # 특정 Element가 None이라면 다시 API를 호출하여 retrialNum만큼 Parsing 재시도.
    def __init__(self, url:str, apiKey: str, retrialNum: int, ignorePreivousReivew: bool, searchInfo: dict=None):
        self.remainingRetrialNum = retrialNum
        self.soup = self.getHTMLParsed(url, apiKey, ignorePreivousReivew, searchInfo)
        while type(self.soup) != int and not self.checkValidity(self.soup, searchInfo is not None) and self.remainingRetrialNum > 0:
            print(f'Retrying request... ({retrialNum - self.remainingRetrialNum + 1}/{retrialNum})')
            self.remainingRetrialNum -= 1
            self.soup = self.getHTMLParsed(url, apiKey, ignorePreivousReivew, searchInfo)
            if self.remainingRetrialNum == 0:
                self.soup = -1

    def getSoup(self):
        return self.soup

    @classmethod
    def getHTMLParsed(cls, url: str, apiKey: str, ignorePreviousReview: bool, searchInfo: dict):
        cls.callNum += 1
        if not ignorePreviousReview:
            if searchInfo is not None:
                params = {
                    'js_render': 'true',
                    'wait': '3000',
                    'premium_proxy': 'true',
                    'js_instructions': '[{"wait_for":"//p[text() = \'Read more\']"},{"evaluate":"document.querySelectorAll(\'p\').forEach(el => { if (el.innerText.includes(\'Read more\')) el.click(); })"}]',
                    'proxy_country': 'us'
                }
            else:
                params = {
                    'js_render': 'true',
                    'wait': '3000',
                    'js_instructions': """[{"wait_for":"//p[text() = 'Read more']"},{"evaluate":"document.querySelectorAll('p').forEach(el => { if (el.innerText.includes('Read more')) el.click(); })"}]""",
                    'premium_proxy': 'true',
                    'proxy_country': 'kr',
                    'custom_headers': 'true'
                }
        else:
            params = {
                'js_render': 'true',
                'wait': '3000',
                'premium_proxy': 'true',
                'js_instructions': """[{"wait_for":"//p[text() = 'Read more']"}]""",
                'proxy_country': 'us'
            }
        headers = {
            'Referer': 'https://google.com'
        }
        client = ZenRowsClient(apiKey)
        response = client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            soup = response.status_code
        else:
            soup = BeautifulSoup(response.text, "html.parser")
        return soup

    @classmethod
    def checkValidity(cls, soup: BeautifulSoup, searchMode: bool):
        try:
            nameElement = soup.find('h1')
            if nameElement is None:
                raise InvalidElementError('Name Element')

            URLElement = soup.find('meta', attrs={'data-rh': 'true', 'property': 'og:url'})
            if URLElement is None:
                raise InvalidElementError('URL Element')

            keepGoing = True
            if searchMode:
                searchResultElement = soup.find_all(lambda tag: tag.name == 'span' and tag.get_text() and "0 reviews mentioning" in tag.get_text())
                if len(searchResultElement) > 0:
                    keepGoing = False
            
            if keepGoing:
                reviewNumElement = soup.find('a', string=re.compile(r'\(\d+ reviews\)'))
                navigationElement = soup.find('div', attrs={'aria-label': 'Pagination navigation'})
                if navigationElement is None and reviewNumElement is not None:
                        raise InvalidElementError('Navigation Element')


                reviewParentElement = soup.find('div', id='reviews')
                if reviewParentElement is None:
                    raise InvalidElementError('Review Parent Element')

                reviewElements = reviewParentElement.select('section > div:nth-of-type(2) > ul > li')
                loadedReviewsNum = len(reviewElements)
                if loadedReviewsNum == 0 and reviewNumElement is not None:
                    raise InvalidElementError('Review Element')

                for reviewElement in reviewElements:
                    if len(reviewElement) == 0:
                        continue
                    userInfoElement = reviewElement.find('div', class_='user-passport-info')
                    if userInfoElement is None:
                        raise InvalidElementError('Review Element')
            return True
        except InvalidElementError as e:
            print(f'[Fail to HTML Parsing] {e}')
            return False
