import interactions
from interactions import Client
from interactions import Extension, listen
from interactions import SlashCommand, SlashContext
from interactions.api.events import Component, ThreadCreate, MessageReactionAdd
from interactions.models.discord.channel import GuildForum

import datetime

#import bet_utils

from . import bet_utils

# The extension class that puts everything together.
class CompetitionExtension(Extension):
    def __init__(self, bot: Client):
        self.bot: Client = bot

        self.channel: GuildForum = None
        self.control_panel: bet_utils.ControlPanel = None

    module_base = SlashCommand(
        name="bet", description="Bet utilities for essay competition."
    )

    @module_base.subcommand(
        sub_cmd_name="bet_module_info", sub_cmd_description="test command, for test only"
    )
    async def bet_module_info(self, ctx: SlashContext):
        full_info_string=self.control_panel.print_competition_info(self.bot)
        await ctx.send(full_info_string)

    @module_base.subcommand(
        sub_cmd_name="bet_module_sync_with_fetch", sub_cmd_description="Update the module data using fetch_channel."
    )
    async def bet_module_sync_with_force_fetch(self, ctx: SlashContext):
        self.channel =await self.bot.fetch_channel(bet_utils.COMPETITION_FORUM_CHANNEL_ID,force=True)
        self.control_panel = bet_utils.ControlPanel(self.channel)

    @module_base.subcommand(
        sub_cmd_name="bet_module_sync_with_get", sub_cmd_description="Update the module data using get_channel."
    )
    async def bet_module_sync_with_get(self, ctx: SlashContext):
        self.channel = self.bot.get_channel(bet_utils.COMPETITION_FORUM_CHANNEL_ID)
        self.control_panel = bet_utils.ControlPanel(self.channel)

    @module_base.subcommand(
        sub_cmd_name="setup_competition",
        sub_cmd_description="Set up the competition bet control panel thread.",
    )
    async def setup_competition(self, ctx: SlashContext):
        self.channel = await self.bot.fetch_channel(bet_utils.COMPETITION_FORUM_CHANNEL_ID,force=True)
        #print(self.channel)
        self.control_panel = bet_utils.ControlPanel(self.channel)
        await self.control_panel.create_control_panel_thread()

    @listen(Component)
    async def on_any_button(self, event: Component):
        ctx = event.ctx
        print(ctx.custom_id)

        if ctx.custom_id == self.control_panel.start_date + ":" + "test":
            temp_participant = bet_utils.Participant(ctx.author.username)
            for aParticipant in self.control_panel.all_participants:
                if temp_participant == aParticipant:
                    temp_participant = aParticipant

            await ctx.send(
                f"Current competition phase is:{str(self.control_panel.phase)}"
                + f"button clicked by:{str(ctx.author.username)},{str(ctx.author.nickname)}"
                + f"user account balance:{temp_participant.balance}",
                delete_after=30,
                ephemeral=True,
            )

        # When 开始比赛 button is clicked, competition starts, bot grant rewards to authors who's already written an article.
        if (
            ctx.custom_id
            == self.control_panel.start_date + ":" + "set_phase:" + "ongoing"
            and self.control_panel.phase == bet_utils.CompetitionPhase.PREMATCH
            and ctx.author.username in bet_utils.ADMINISTRATORS_LIST
        ):
            print(f"Competition started.")
            self.control_panel.phase = bet_utils.CompetitionPhase.ONGOING
            all_existing_threads = await self.channel.fetch_posts()
            for aThread in all_existing_threads:

                print(aThread.created_at.strftime("%Y-%m-%d"))
                acceptable_thread_threshold_date = datetime.datetime.strptime(
                    self.control_panel.start_date, "%Y-%m-%d"
                ) - datetime.timedelta(
                    days=bet_utils.LOAD_PREMATURE_THREADS_DAYS_THRESHOLD
                )

                if aThread.created_at.date() > acceptable_thread_threshold_date.date():
                    temp_thread_id = aThread.id
                    temp_thread_message = await aThread.fetch_message(temp_thread_id)

                    temp_participant = bet_utils.Participant(
                        str(temp_thread_message.author.username)
                    )

                    # Controversial!!!: removing existing reactions!!!
                    # bet_utils.remove_premature_reactions(temp_thread_message)

                    await bet_utils.grant_reward_to_article_author(
                        temp_participant,
                        temp_thread_message,
                        self.control_panel.all_participants,
                        bet_utils.ARTICLE_VALIDITY_THRESHOLD,
                        bet_utils.ARTICLE_AUTHOR_REWARD,
                    )
                    await self.control_panel.add_new_bet_option_ui(aThread)

        elif (
            ctx.custom_id
            == self.control_panel.start_date + ":" + "set_phase:" + "grading"
            and self.control_panel.phase == bet_utils.CompetitionPhase.ONGOING
            and ctx.author.username in bet_utils.ADMINISTRATORS_LIST
        ):
            self.control_panel.phase = bet_utils.CompetitionPhase.GRADING

        elif (
            ctx.custom_id
            == self.control_panel.start_date + ":" + "set_phase:" + "concluding"
            and self.control_panel.phase == bet_utils.CompetitionPhase.GRADING
            and ctx.author.username in bet_utils.ADMINISTRATORS_LIST
        ):
            self.control_panel.phase = bet_utils.CompetitionPhase.CONCLUDING

            winner_thread_id: int = await self.control_panel.send_announcement_modal(
                event
            )

            if winner_thread_id not in self.control_panel.all_articles_thread_id:
                await ctx.send(
                    content=f"您输入的文章贴id:{winner_thread_id}不存在，请核查确认",
                    delete_after=30,
                    ephemeral=True,
                )
                self.control_panel.phase = bet_utils.CompetitionPhase.GRADING

            await bet_utils.grant_reward_to_winner_author(
                winner_thread_id, self.control_panel, bet_utils.WINNER_AUTHOR_REWARD
            )
            self.control_panel.calculate_odds()
            self.control_panel.distribute_bet_rewards(winner_thread_id)

            temp_competition_result = ""

            for aParticipant in self.control_panel.all_participants:
                temp_competition_result += f" {{ username:\"{str(aParticipant.username)}\", balance:{aParticipant.balance} }}" + "\n"

            print(temp_competition_result)

            await ctx.send(temp_competition_result)

            await self.control_panel.write_participants_balance_json(
                self.control_panel.all_participants
            )

        elif ctx.custom_id == self.control_panel.start_date + ":" + "collect_ubi":
            temp_participant = bet_utils.Participant(str(ctx.author.username))

            if temp_participant not in self.control_panel.all_participants:
                await temp_participant.collect_ubi(event)
                self.control_panel.all_participants.append(temp_participant)
            else:
                for aParticipant in self.control_panel.all_participants:
                    if (
                        aParticipant == temp_participant
                        and not aParticipant.already_UBIed
                    ):
                        await aParticipant.collect_ubi(event)

        elif ctx.custom_id[:3] == "bet":
            await self.control_panel.send_bet_modal(event)

    @listen(ThreadCreate)
    async def on_new_thread(self, event: ThreadCreate):
        if self.channel != event.thread.parent_channel:
            print("Thread filtered.")
        else:
            temp_thread_id = event.thread.id
            temp_thread_message = await event.thread.fetch_message(temp_thread_id)
            temp_username = str(temp_thread_message.author.username)
            temp_participant = bet_utils.Participant(temp_username)

            if self.control_panel.phase == bet_utils.CompetitionPhase.ONGOING:
                await self.control_panel.add_new_bet_option_ui(event.thread)
                await bet_utils.grant_reward_to_article_author(
                    temp_participant,
                    temp_thread_message,
                    self.control_panel.all_participants,
                    bet_utils.ARTICLE_VALIDITY_THRESHOLD,
                    bet_utils.ARTICLE_AUTHOR_REWARD,
                )

    """@listen(MessageReactionAdd)
    async def on_reaction_added(self, event: MessageReactionAdd):
        temp_message = event.message
        temp_message_id = event.message.id
        if (
            self.control_panel.phase == bet_utils.CompetitionPhase.ONGOING
            and temp_message_id in self.control_panel.all_articles_thread_id
        ):
            await bet_utils.remove_premature_reactions(temp_message)"""
