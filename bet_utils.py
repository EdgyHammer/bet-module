from interactions import Message, Client
from interactions import ActionRow, Button, ButtonStyle
from interactions import Modal, ShortText, ModalContext
from interactions.api.events import Component
from interactions.models.discord.channel import GuildForum, GuildForumPost
from enum import IntEnum
from typing import List, Dict
import json
import aiofiles
import os
import asyncio
import datetime


BET_PARTICIPANTS_BALANCE_DATABASE_PATH= f"{os.path.dirname(__file__)}/participants_balance.json"

COMPETITION_GUILD_ID: int = 1200434448425033788
COMPETITION_FORUM_CHANNEL_ID: int = 1228907795563151511
#COMPETITION_GUILD_ID: int = 1150630510696075404
#COMPETITION_FORUM_CHANNEL_ID: int = 1227479189746356224

ARTICLE_VALIDITY_THRESHOLD: int = 500
ARTICLE_AUTHOR_REWARD: float = 300
WINNER_AUTHOR_REWARD: float = 1000
COMPENSATION_PER_REACTION: float=50
LOAD_PREMATURE_THREADS_DAYS_THRESHOLD=7
ADMINISTRATORS_LIST:List[str]=["edgyhammer","dichnlz"]


class CompetitionPhase(IntEnum):
    PREMATCH = 1
    ONGOING = 2
    GRADING = 3
    CONCLUDING = 4

# A participant class to store and manage user data (currently in ram only).
class Participant:
    def __init__(self, username: str):
        self.is_article_author: bool = False
        self.already_UBIed: bool = False
        self.balance: float = 0
        self.username: str = username
        self.bet_choices: dict = {}

    def bet(self, thread_id: int, amount: float):
        self.bet_choices[thread_id] = amount
        self.balance -= amount

    def collect_bet_reward(self, winner_thread_id: int, odds: float):
        if winner_thread_id in self.bet_choices:
            self.balance += round(self.bet_choices[winner_thread_id] * odds,2)

    async def collect_ubi(self, event: Component):
        if not self.already_UBIed:
            self.balance += 100
            self.already_UBIed = True
            await event.ctx.send('成功领取100枚代币', delete_after=10, ephemeral=True)
        else:
            await event.ctx.send('不能重复领取代币，您可以发表文章获取额外300代币。', delete_after=10, ephemeral=True)

    def __str__(self):
        temp_dict = {
            'user id': self.username,
            'is content creator': self.is_article_author,
            'already UBIed': self.already_UBIed,
            'balance': self.balance,
            'bet on': self.bet_choices
        }
        temp_str = f"{temp_dict}"
        return temp_str

    def __eq__(self, other):
        try:
            if self.username == other.username:
                return True
        except TypeError:
            print('User type mismatch')

# # A control panel class to manage the control panel thread, within which all the bet-related activities, both user-wise and
# administrator-wise, are conducted.
class ControlPanel:
    def __init__(self, channel: GuildForum):
        self.thread_title: str = '投注站'
        self.thread_content: str = '比赛投稿阶段，任何成员均可从此处领取总计100枚竞猜代币，此代币可以用于押注本次比赛的优胜文章。'
        self.start_date: str = datetime.datetime.today().strftime("%Y-%m-%d")
        self.channel: GuildForum = channel
        self.thread: GuildForumPost = None
        self.all_participants: List[Participant] = []
        self.all_articles_thread_id: List[int] = []
        self.all_bets_vs_thread_id: Dict[int, float] = {}
        self.all_odds_vs_thread_id: Dict[int, float] = {}
        self.phase = CompetitionPhase.PREMATCH
        # # A GUI thread for admins to manage the events, including closing the betting session, announcing the end of the event, the winner.
        # # In side this same GUI thread, there should be also a CLI output of the current status of each competitor, i.e. the total bet amount,
        # # the number of members betting for this competitor and the odds.
        self.main_menu_ui: list[ActionRow] = [
            ActionRow(
                Button(
                    custom_id=self.start_date+":"+'test',
                    style=ButtonStyle.GREEN,
                    label='测试'
                ),
                Button(
                    custom_id=self.start_date+":"+'collect_ubi',
                    style=ButtonStyle.GREEN,
                    label='领取代币'
                ),
                Button(
                    custom_id=self.start_date+":"+'set_phase:' + 'ongoing',
                    style=ButtonStyle.GREEN,
                    label='开始比赛'
                ),
                Button(
                    custom_id=self.start_date+":"+'set_phase:' + 'grading',
                    style=ButtonStyle.RED,
                    label='开放投票'
                ),
                Button(
                    custom_id=self.start_date+":"+'set_phase:' + 'concluding',
                    style=ButtonStyle.BLURPLE,
                    label='公布结果'
                )
            )
        ]

    # On competition setup completion and turned into pre-match phase, bot creates a control panel thread, where admin can manage the competition
    # and members can bet.
    async def create_control_panel_thread(self):
        post: GuildForumPost = await self.channel.create_post(name=self.thread_title, content=self.thread_content, components=self.main_menu_ui)
        self.thread = post

    def print_competition_info(self,bot:Client):

        full_info_string=f"1st_guild_id:{str(bot.guilds[0].id)}, channel_id:{self.channel.id}, phase:{self.phase}, date{self.start_date}"
        #print(self.thread, self.phase, self.channel, self.start_date, self.all_articles_thread_id, self.all_participants)
        for aParticipant in self.all_participants:
            print(aParticipant)

        full_info_string+="\n"+"all guilds:"+"\n"
        for aGuild in bot.guilds:
            full_info_string+=str(aGuild.id)+"\n"

        return full_info_string

    # # Buttons manager: add buttons to each thread of essay. Buttons including the bet for this thread button,
    # # A button will provoke a bet modal, asking the participants for bet amount.
    async def add_new_bet_option_ui(self, article_thread: GuildForumPost):
        temp_thread_id: int = article_thread.id
        temp_initial_message = await article_thread.fetch_message(temp_thread_id)
        temp_article_author_id: str = str(temp_initial_message.author.username)
        temp_article_title: str = article_thread.name
        temp_url = f"https://discord.com/channels/{COMPETITION_FORUM_CHANNEL_ID}/{temp_thread_id}"
        item_ui = [
            ActionRow(
                Button(
                    custom_id='bet' + str(temp_thread_id),
                    style=ButtonStyle.BLUE,
                    label='押注此文'
                )
            )
        ]
        if len(temp_initial_message.content) > ARTICLE_VALIDITY_THRESHOLD:
            await self.thread.send(content=f'{temp_article_author_id}\n{temp_article_title}\n{temp_url}\n', components=item_ui)
            self.all_articles_thread_id.append(temp_thread_id)

    async def send_bet_modal(self, event: Component):
        ctx = event.ctx
        bet_modal = Modal(
            ShortText(label="押注金额", value="0", custom_id="amount_input"),
            title="确认押注金额",
        )
        await ctx.send_modal(modal=bet_modal)
        modal_ctx: ModalContext = await ctx.bot.wait_for_modal(bet_modal)

        amount = 0
        try:
            amount = int(modal_ctx.responses["amount_input"])
        except ValueError:
            await modal_ctx.send('请输入整数。', delete_after=5, ephemeral=True)
        temp_username = modal_ctx.author.username
        temp_participant = Participant(temp_username)

        if temp_participant not in self.all_participants:
            await modal_ctx.send('您还没有用于押注的代币，请用本帖的领取代币按钮领取100代币（仅限一次），或参与投稿获得300代币。', delete_after=5,
                                 ephemeral=True)
        else:
            for aParticipant in self.all_participants:
                if aParticipant == temp_participant:
                    if aParticipant.balance < amount:
                        await modal_ctx.send(f'您有{aParticipant.balance}个代币，请用本帖的领取代币按钮领取100代币（仅限一次），或参与投稿获得300代币。',
                                             delete_after=5,
                                             ephemeral=True)
                    else:
                        bet_on_thread_id = int(event.ctx.custom_id[3:])
                        temp_url = f"https://discord.com/channels/{COMPETITION_FORUM_CHANNEL_ID}/{bet_on_thread_id}"
                        await modal_ctx.send(f'您使用{amount}个代币押注了{temp_url}',
                                             delete_after=5,
                                             ephemeral=True)
                        aParticipant.bet(bet_on_thread_id, float(amount))

    async def send_announcement_modal(self, event: Component):
        ctx = event.ctx
        announcement_modal = Modal(
            ShortText(label="优胜文章id", value="1234567890123", custom_id="winner_thread_id"),
            title="宣布获奖文章",
        )
        await ctx.send_modal(modal=announcement_modal)
        modal_ctx: ModalContext = await ctx.bot.wait_for_modal(announcement_modal)

        try:
            temp_winner_thread_id = int(modal_ctx.responses["winner_thread_id"])
            
        except ValueError:
            await modal_ctx.send('请输入整数。', delete_after=5, ephemeral=True)
        return temp_winner_thread_id

    # # An odds calculator
    def calculate_odds(self):
        total_bet = 0
        for aParticipant in self.all_participants:
            for aThread in aParticipant.bet_choices:
                if aThread not in self.all_bets_vs_thread_id:
                    self.all_bets_vs_thread_id[aThread] = aParticipant.bet_choices[aThread]
                    total_bet += aParticipant.bet_choices[aThread]
                elif aThread in self.all_bets_vs_thread_id:
                    self.all_bets_vs_thread_id[aThread] += aParticipant.bet_choices[aThread]
                    total_bet += aParticipant.bet_choices[aThread]

        for aThread in self.all_bets_vs_thread_id:
            if self.all_bets_vs_thread_id[aThread]!=0:
                self.all_odds_vs_thread_id[aThread] = total_bet / self.all_bets_vs_thread_id[aThread]

    def distribute_bet_rewards(self, winner_article_thread_id: int):
        if len(self.all_odds_vs_thread_id)>0:
            winner_odd = self.all_odds_vs_thread_id[winner_article_thread_id]
            for aParticipant in self.all_participants:
                aParticipant.collect_bet_reward(winner_article_thread_id, winner_odd)
        else:
            pass


    # A user database manager class, similar to the one used in stock manager.
    async def write_participants_balance_json(self,all_participants: List[Participant]):
        temp_dict: dict = {}
        for aParticipant in all_participants:
            temp_dict[aParticipant.username] = aParticipant.balance
        
        async with aiofiles.open(BET_PARTICIPANTS_BALANCE_DATABASE_PATH, 'w', encoding='utf-8') as f:
            json_data = json.dumps(temp_dict, ensure_ascii=False, indent=4)
            await f.write(json_data)


# Algorithms to actually make things happen.
# # A premature reactions remover
async def remove_premature_reactions(reaction_found_on_threadmessage: Message):
    await reaction_found_on_threadmessage.clear_all_reactions()


# # Grant reward to content creator
async def grant_reward_to_article_author(
        article_author: Participant,
        article_message: Message,
        existing_participants: List[Participant],
        threshold: int,
        amount: float
):
    if article_author not in existing_participants:

        if len(article_message.content) >= threshold:
            article_author.is_article_author = True
            article_author.balance += amount
            existing_participants.append(article_author)

    else:
        for aParticipant in existing_participants:
            if aParticipant == article_author and not aParticipant.is_article_author:
                if len(article_message.content) >= threshold:
                    aParticipant.is_article_author = True
                    aParticipant.balance += amount

# # Grant reward to content creator
async def grant_reward_to_winner_author(
        winner_thread_id: int,
        control_panel: ControlPanel,
        amount: float=WINNER_AUTHOR_REWARD
): 
    winner_thread:GuildForumPost=await control_panel.channel.fetch_post(winner_thread_id)
    winner_message:Message = await winner_thread.fetch_message(winner_thread_id)
    winner_username:str=winner_message.author.username

    temp_participant:Participant=Participant(winner_username)
            
    for aParticipant in control_panel.all_participants:
        if aParticipant == temp_participant:
            aParticipant.balance += amount