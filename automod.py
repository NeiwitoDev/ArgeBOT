import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
from datetime import datetime, timedelta
from collections import defaultdict
import re
import json
import os

# ====================== CONFIGURACIÓN POR DEFECTO ======================
FLOOD_LIMIT = 5
FLOOD_SECONDS = 6
# =======================================================================

user_messages = defaultdict(list)


def load_automod():
    if not os.path.exists("automod.json"):
        return {}
    with open("automod.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_automod(data):
    with open("automod.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


class AutoModConfigPanel(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = str(guild_id)

    @discord.ui.button(label="Canal de Logs", style=discord.ButtonStyle.primary)
    async def set_logs(self, interaction: discord.Interaction, button: Button):
        view = ChannelSelectView(self.guild_id, "logs")
        await interaction.response.send_message("Selecciona el canal de logs de sanciones:", view=view, ephemeral=True)

    @discord.ui.button(label="Activar/Desactivar", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button: Button):
        data = load_automod()
        if self.guild_id not in data:
            data[self.guild_id] = {}
        current = data[self.guild_id].get("enabled", True)
        data[self.guild_id]["enabled"] = not current
        save_automod(data)
        estado = "activado" if not current else "desactivado"
        await interaction.response.send_message(f"AutoMod **{estado}**.", ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, button: Button):
        data = load_automod()
        if self.guild_id in data:
            del data[self.guild_id]
            save_automod(data)
        await interaction.response.send_message("Configuración de AutoMod reiniciada.", ephemeral=True)


class ChannelSelectView(View):
    def __init__(self, guild_id, mode):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.mode = mode

        select = ChannelSelect(
            placeholder="Selecciona el canal",
            channel_types=[discord.ChannelType.text],
            max_values=1,
            min_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        data = load_automod()
        if self.guild_id not in data:
            data[self.guild_id] = {}

        selected = str(self.children[0].values[0].id)

        if self.mode == "logs":
            data[self.guild_id]["log_channel"] = selected
            save_automod(data)
            await interaction.response.edit_message(content=f"Canal de logs configurado: <#{selected}>", view=None)


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_exempt(self, member: discord.Member, channel: discord.TextChannel) -> bool:
        if member.guild_permissions.administrator or member.guild_permissions.manage_messages:
            return True
        return False

    def contains_invite(self, content: str) -> bool:
        patterns = [
            r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)[a-zA-Z0-9-]+",
            r"(dsc\.gg/)[a-zA-Z0-9-]+"
        ]
        return any(re.search(p, content, re.IGNORECASE) for p in patterns)

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        data = load_automod().get(str(guild.id), {})
        channel_id = data.get("log_channel")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=embed)
            except:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        data = load_automod().get(str(message.guild.id), {})
        if data.get("enabled", True) is False:
            return

        if self.is_exempt(message.author, message.channel):
            return

        # ---------- SPAM DE INVITACIONES ----------
        if self.contains_invite(message.content):
            try:
                await message.delete()
            except:
                pass

            warn_embed = discord.Embed(
                description=f"{message.author.mention} Hey! Nuestro sistema detectó **spam de enlaces** de tu parte... fuiste advertido automáticamente.",
                color=0xff5555,
                timestamp=datetime.utcnow()
            )
            warn_embed.set_footer(text="Sistema AutoMod")
            try:
                await message.channel.send(embed=warn_embed, delete_after=8)
            except:
                pass

            log_embed = discord.Embed(title="🚫 Spam de invitación detectado", color=0xff5555, timestamp=datetime.utcnow())
            log_embed.add_field(name="Usuario", value=f"{message.author} (`{message.author.id}`)", inline=False)
            log_embed.add_field(name="Canal", value=message.channel.mention, inline=True)
            log_embed.add_field(name="Contenido", value=message.content[:1000] or "N/A", inline=False)
            await self.send_log(message.guild, log_embed)
            return

        # ---------- FLOOD ----------
        user_id = message.author.id
        now = datetime.utcnow()

        user_messages[user_id] = [
            t for t in user_messages[user_id]
            if now - t < timedelta(seconds=FLOOD_SECONDS)
        ]
        user_messages[user_id].append(now)

        if len(user_messages[user_id]) >= FLOOD_LIMIT:
            def check(m):
                return m.author.id == user_id and (now - m.created_at.replace(tzinfo=None)) < timedelta(seconds=FLOOD_SECONDS + 2)

            try:
                await message.channel.purge(limit=25, check=check)
            except:
                try:
                    await message.delete()
                except:
                    pass

            warn_embed = discord.Embed(
                description=f"{message.author.mention} Hey! Nuestro sistema detectó **flood** de tu parte... fuiste advertido automáticamente.",
                color=0xffaa00,
                timestamp=datetime.utcnow()
            )
            warn_embed.set_footer(text="Sistema AutoMod • Flood detectado")
            try:
                await message.channel.send(embed=warn_embed, delete_after=10)
            except:
                pass

            log_embed = discord.Embed(title="⚠️ Flood detectado", color=0xffaa00, timestamp=datetime.utcnow())
            log_embed.add_field(name="Usuario", value=f"{message.author} (`{message.author.id}`)", inline=False)
            log_embed.add_field(name="Canal", value=message.channel.mention, inline=True)
            log_embed.add_field(name="Mensajes", value=str(FLOOD_LIMIT), inline=True)
            await self.send_log(message.guild, log_embed)

            user_messages[user_id].clear()

    @app_commands.command(name="config-automod", description="Configura el sistema de AutoMod")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_automod(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        data = load_automod().get(guild_id, {})

        embed = discord.Embed(
            title="⚙️ Panel de AutoMod",
            description="Configura el sistema de moderación automática.",
            color=0x5865F2
        )
        embed.add_field(
            name="Estado",
            value="🟢 Activado" if data.get("enabled", True) else "🔴 Desactivado",
            inline=True
        )
        embed.add_field(
            name="Canal de Logs",
            value=f"<#{data['log_channel']}>" if data.get("log_channel") else "No configurado",
            inline=True
        )
        embed.add_field(
            name="Flood",
            value=f"{FLOOD_LIMIT} mensajes en {FLOOD_SECONDS}s",
            inline=False
        )

        await interaction.response.send_message(embed=embed, view=AutoModConfigPanel(interaction.guild.id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
