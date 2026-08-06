import discord
from discord.ext import commands
from datetime import datetime, timedelta
from collections import defaultdict
import re

# ====================== CONFIGURACIÓN ======================
FLOOD_LIMIT = 5          # Mensajes
FLOOD_SECONDS = 5        # En cuántos segundos se considera flood
SPAM_WARN_MESSAGE = "Hey! Nuestro sistema detectó **flood** de tu parte... fuiste advertido automáticamente."
LINK_WARN_MESSAGE = "Hey! Nuestro sistema detectó **spam de enlaces** de tu parte... fuiste advertido automáticamente."

# Canales donde el AutoMod NO actúa (pon los IDs)
IGNORED_CHANNELS = []

# Roles que están exentos del AutoMod (pon los IDs)
IGNORED_ROLES = []

# ====================== ALMACENAMIENTO EN MEMORIA ======================
user_messages = defaultdict(list)   # {user_id: [timestamps]}


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_exempt(self, member: discord.Member, channel: discord.TextChannel) -> bool:
        """Comprueba si el usuario o el canal están exentos"""
        if channel.id in IGNORED_CHANNELS:
            return True
        if any(role.id in IGNORED_ROLES for role in member.roles):
            return True
        if member.guild_permissions.administrator or member.guild_permissions.manage_messages:
            return True
        return False

    def contains_invite(self, content: str) -> bool:
        """Detecta invitaciones de Discord"""
        patterns = [
            r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)[a-zA-Z0-9]+",
            r"(dsc\.gg/)[a-zA-Z0-9]+"
        ]
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.is_exempt(message.author, message.channel):
            return

        # ---------- DETECCIÓN DE SPAM DE LINKS ----------
        if self.contains_invite(message.content):
            try:
                await message.delete()
            except:
                pass

            warn_embed = discord.Embed(
                description=f"{message.author.mention} {LINK_WARN_MESSAGE}",
                color=0xff5555,
                timestamp=datetime.utcnow()
            )
            warn_embed.set_footer(text="Sistema AutoMod")
            try:
                await message.channel.send(embed=warn_embed, delete_after=8)
            except:
                pass
            return

        # ---------- DETECCIÓN DE FLOOD ----------
        user_id = message.author.id
        now = datetime.utcnow()

        # Limpiar mensajes antiguos
        user_messages[user_id] = [
            t for t in user_messages[user_id]
            if now - t < timedelta(seconds=FLOOD_SECONDS)
        ]

        user_messages[user_id].append(now)

        if len(user_messages[user_id]) >= FLOOD_LIMIT:
            # Eliminar los mensajes recientes del usuario en el canal
            def is_user_message(m):
                return m.author.id == user_id and (now - m.created_at.replace(tzinfo=None)) < timedelta(seconds=FLOOD_SECONDS + 2)

            try:
                await message.channel.purge(limit=20, check=is_user_message)
            except:
                try:
                    await message.delete()
                except:
                    pass

            # Enviar advertencia
            warn_embed = discord.Embed(
                description=f"{message.author.mention} {SPAM_WARN_MESSAGE}",
                color=0xffaa00,
                timestamp=datetime.utcnow()
            )
            warn_embed.set_footer(text="Sistema AutoMod • Flood detectado")
            try:
                await message.channel.send(embed=warn_embed, delete_after=10)
            except:
                pass

            # Limpiar historial del usuario para que no se repita inmediatamente
            user_messages[user_id].clear()


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
