import interactions
from interactions import Client
from interactions import Extension, listen
from interactions import SlashCommand, SlashContext
from interactions.api.events import Component, ThreadCreate, MessageReactionAdd
from interactions.models.discord.channel import GuildForum

import json
import aiofiles
import asyncio
import datetime
import os
import re

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
        sub_cmd_name="test", sub_cmd_description="test command, for test only"
    )
    async def test(self, ctx: SlashContext):
        self.control_panel.print_competition_info()

    @module_base.subcommand(
        sub_cmd_name="setup_competition",
        sub_cmd_description="Set up the competition bet control panel thread.",
    )
    async def setup_competition(self, ctx: SlashContext):
        self.channel = self.bot.get_channel(bet_utils.COMPETITION_FORUM_CHANNEL_ID)
        print(self.channel)
        self.control_panel = bet_utils.ControlPanel(self.channel)
        await self.control_panel.create_control_panel_thread()

    @listen(Component)
    async def on_any_button(self, event: Component):
        ctx = event.ctx
        print(ctx.custom_id)

        if ctx.custom_id == "test" + self.control_panel.start_date:
            await ctx.send(
                f"Current competition phase is:{str(self.control_panel.phase)}, button clicked by:{str(ctx.author.username)},{str(ctx.author.nickname)}",
                ephemeral=True,
            )

        # When 开始比赛 button is clicked, competition starts, bot grant rewards to authors who's already written an article.
        if (
            ctx.custom_id == "set_phase:" + "ongoing"
            and self.control_panel.phase != bet_utils.CompetitionPhase.ONGOING
        ):
            print(f"Competition started.")
            self.control_panel.phase = bet_utils.CompetitionPhase.ONGOING
            all_existing_threads = await self.channel.fetch_posts()
            for aThread in all_existing_threads:
                temp_thread_id = aThread.id
                temp_thread_message = await aThread.fetch_message(temp_thread_id)
                temp_participant = bet_utils.Participant(
                    str(temp_thread_message.author.username)
                )
                await bet_utils.grant_reward_to_article_author(
                    temp_participant,
                    temp_thread_message,
                    self.control_panel.all_participants,
                    bet_utils.ARTICLE_VALIDITY_THRESHOLD,
                    bet_utils.ARTICLE_AUTHOR_REWARD,
                )
                await self.control_panel.add_new_bet_option_ui(aThread)

        elif ctx.custom_id == "set_phase:" + "grading":
            self.control_panel.phase = bet_utils.CompetitionPhase.GRADING

        elif ctx.custom_id == "set_phase:" + "concluding":
            self.control_panel.phase = bet_utils.CompetitionPhase.CONCLUDING
            await self.control_panel.send_announcement_modal(event)

            temp_competition_result = ""

            for aParticipant in self.control_panel.all_participants:
                temp_competition_result += str(aParticipant.balance) + "\n"

            print(temp_competition_result)

            await ctx.send(temp_competition_result)

        elif ctx.custom_id == "collect_ubi":
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

    @listen(MessageReactionAdd)
    async def on_reaction_added(self, event: MessageReactionAdd):
        temp_message = event.message
        temp_message_id = event.message.id
        if (
            self.control_panel.phase == bet_utils.CompetitionPhase.ONGOING
            and temp_message_id in self.control_panel.all_articles_thread_id
        ):
            await bet_utils.remove_premature_reactions(temp_message)
