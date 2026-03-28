"""
Discord moderation bot using the ice9 baseline tier.

Screens every image attachment posted to your server. If ice9 flags
explicit content above the confidence threshold, the message is deleted and
the user is notified in a DM.

Requirements:
    pip install ice9 "discord.py>=2.0" Pillow

Environment variables:
    ICE9_API_KEY     — your ice9 API key
    DISCORD_TOKEN    — your Discord bot token

Bot permissions required (in the Discord developer portal):
    - Read Messages / View Channels
    - Manage Messages (to delete flagged posts)
    - Send Messages
    - Send Messages in Threads
    - Read Message History

Enable the following Privileged Gateway Intents:
    - Message Content Intent

Usage:
    ICE9_API_KEY=... DISCORD_TOKEN=... python examples/discord_bot.py
"""

import asyncio
import io
import logging
import os

import discord

from ice9 import Ice9, CENSOR_LABELS
from ice9.exceptions import Ice9Error, ImageRejectedError, PartialResultError

# ---------------------------------------------------------------------------
# Configuration

MIN_CONFIDENCE = 0.5    # nudenet confidence threshold — detections below this are ignored
NOTIFY_USER    = True   # DM the user when their post is removed
LOG_CHANNEL_ID = None   # optional int channel ID to post moderation logs; None = disabled

# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("ice9-bot")

ice9 = Ice9()  # reads ICE9_API_KEY from environment


def is_image(attachment):
    return attachment.content_type is not None and attachment.content_type.startswith("image/")


def get_flagged_detections(result):
    """Return detections that are in CENSOR_LABELS and above MIN_CONFIDENCE."""
    if result.nudenet is None:
        return []
    return result.nsfw_detections(labels=CENSOR_LABELS, min_confidence=MIN_CONFIDENCE)


async def screen_attachment(attachment):
    """Download attachment and run ice9 analysis. Returns (flagged, detections)."""
    data = await attachment.read()
    fp = io.BytesIO(data)
    fp.name = attachment.filename  # requests uses filename to set Content-Type

    # ice9.analyze() is a blocking call, so we run it in a background thread
    # to avoid freezing the bot while waiting for the API response.
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: ice9.analyze(fp),
        )
    except PartialResultError as e:
        log.warning("Partial result for %s: %s", attachment.filename, e)
        result = e.result
    except ImageRejectedError:
        log.info("ice9 rejected %s (not an image or too small)", attachment.filename)
        return False, []
    except Ice9Error as e:
        log.error("ice9 error screening %s: %s", attachment.filename, e)
        return False, []

    detections = get_flagged_detections(result)
    return bool(detections), detections


class ModerationBot(discord.Client):

    async def on_ready(self):
        log.info("Logged in as %s (id=%s)", self.user, self.user.id)

    async def on_message(self, message):
        if message.author.bot:
            return

        image_attachments = [a for a in message.attachments if is_image(a)]
        if not image_attachments:
            return

        for attachment in image_attachments:
            flagged, detections = await screen_attachment(attachment)
            if not flagged:
                continue

            # Build a sorted, deduplicated list of label names for logging/messaging
            label_names = sorted(set(d["label"] for d in detections))
            label_list = ", ".join(label_names)

            log.info(
                "Flagged message %s in #%s from %s — labels: %s",
                message.id,
                message.channel,
                message.author,
                label_list,
            )

            try:
                await message.delete()
            except discord.Forbidden:
                log.warning("Missing Manage Messages permission in #%s", message.channel)
                continue
            except discord.NotFound:
                pass  # already deleted

            if NOTIFY_USER:
                try:
                    await message.author.send(
                        f"Your image in **{message.guild.name} #{message.channel.name}** "
                        f"was removed because it contained content that isn't allowed here "
                        f"({label_list})."
                    )
                except discord.Forbidden:
                    pass  # user has DMs disabled

            if LOG_CHANNEL_ID:
                log_channel = self.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    await log_channel.send(
                        f"🛡 Removed image from {message.author.mention} "
                        f"in {message.channel.mention} — {label_list}"
                    )

            # Only act on the first flagged attachment per message to avoid
            # double-deletion races on multi-attachment posts.
            break


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN environment variable is required")

    intents = discord.Intents.default()
    intents.message_content = True

    bot = ModerationBot(intents=intents)
    bot.run(token)


if __name__ == "__main__":
    main()
