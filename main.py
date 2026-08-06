import os
import json
import re
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(command_prefix="?", intents=intents)
tree = bot.tree

# ====================== BASE DE DATOS JSON ======================
def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ====================== UTILIDAD: CONVERTIR TIEMPO ======================
def parse_time(tiempo: str):
    """Convierte 10m, 1h, 2d, 30s a timedelta"""
    if not tiempo:
        return None
    match = re.match(r"(\d+)([smhd])", tiempo.lower())
    if not match:
        return None
    cantidad, unidad = int(match.group(1)), match.group(2)
    if unidad == "s":
        return timedelta(seconds=cantidad)
    if unidad == "m":
        return timedelta(minutes=cantidad)
    if unidad == "h":
        return timedelta(hours=cantidad)
    if unidad == "d":
        return timedelta(days=cantidad)
    return None

# ====================== SISTEMA DE BIENVENIDAS ======================
class WelcomePanel(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = str(guild_id)

    @discord.ui.button(label="Canal", style=discord.ButtonStyle.primary)
    async def set_channel(self, interaction: discord.Interaction, button: Button):
        view = ChannelSelectView(self.guild_id, "channel")
        await interaction.response.send_message("Selecciona el canal de bienvenidas:", view=view, ephemeral=True)

    @discord.ui.button(label="Mensaje", style=discord.ButtonStyle.primary)
    async def set_message(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MessageModal(self.guild_id))

    @discord.ui.button(label="Color", style=discord.ButtonStyle.primary)
    async def set_color(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ColorModal(self.guild_id))

    @discord.ui.button(label="Título", style=discord.ButtonStyle.secondary)
    async def set_title(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TitleModal(self.guild_id))

    @discord.ui.button(label="Imagen", style=discord.ButtonStyle.secondary)
    async def set_image(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ImageModal(self.guild_id))

    @discord.ui.button(label="Canales recomendados", style=discord.ButtonStyle.secondary)
    async def set_recommended(self, interaction: discord.Interaction, button: Button):
        view = ChannelSelectView(self.guild_id, "recommended")
        await interaction.response.send_message("Selecciona hasta 10 canales recomendados:", view=view, ephemeral=True)

    @discord.ui.button(label="Probar", style=discord.ButtonStyle.success)
    async def test_welcome(self, interaction: discord.Interaction, button: Button):
        await send_welcome(interaction.user, interaction.guild)
        await interaction.response.send_message("Mensaje de prueba enviado.", ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, button: Button):
        data = load_json("welcome.json")
        if self.guild_id in data:
            del data[self.guild_id]
            save_json("welcome.json", data)
        await interaction.response.send_message("Configuración reiniciada.", ephemeral=True)


class ChannelSelectView(View):
    def __init__(self, guild_id, mode):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.mode = mode

        select = ChannelSelect(
            placeholder="Selecciona canal(es)",
            channel_types=[discord.ChannelType.text],
            max_values=10 if mode == "recommended" else 1,
            min_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        data = load_json("welcome.json")
        if self.guild_id not in data:
            data[self.guild_id] = {}

        selected = [str(c.id) for c in self.children[0].values]

        if self.mode == "channel":
            data[self.guild_id]["channel_id"] = selected[0]
            save_json("welcome.json", data)
            await interaction.response.edit_message(content=f"Canal configurado: <#{selected[0]}>", view=None)
        else:
            data[self.guild_id]["recommended"] = selected
            save_json("welcome.json", data)
            await interaction.response.edit_message(content="Canales recomendados guardados.", view=None)


class MessageModal(Modal, title="Mensaje de bienvenida"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        data = load_json("welcome.json").get(guild_id, {})
        self.message = TextInput(
            label="Mensaje (usa {user} {server} {count})",
            style=discord.TextStyle.paragraph,
            default=data.get("message", "¡Bienvenido {user} a **{server}**!"),
            required=True,
            max_length=2000
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_json("welcome.json")
        if self.guild_id not in data:
            data[self.guild_id] = {}
        data[self.guild_id]["message"] = self.message.value
        save_json("welcome.json", data)
        await interaction.response.send_message("Mensaje actualizado.", ephemeral=True)


class ColorModal(Modal, title="Color del embed"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        data = load_json("welcome.json").get(guild_id, {})
        self.color = TextInput(
            label="Color HEX (ej: #00ff00)",
            default=data.get("color", "#00ff00"),
            required=True,
            max_length=7
        )
        self.add_item(self.color)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_json("welcome.json")
        if self.guild_id not in data:
            data[self.guild_id] = {}
        data[self.guild_id]["color"] = self.color.value
        save_json("welcome.json", data)
        await interaction.response.send_message("Color actualizado.", ephemeral=True)


class TitleModal(Modal, title="Título del embed"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        data = load_json("welcome.json").get(guild_id, {})
        self.title_input = TextInput(
            label="Título",
            default=data.get("title", "¡Bienvenido!"),
            required=True,
            max_length=256
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_json("welcome.json")
        if self.guild_id not in data:
            data[self.guild_id] = {}
        data[self.guild_id]["title"] = self.title_input.value
        save_json("welcome.json", data)
        await interaction.response.send_message("Título actualizado.", ephemeral=True)


class ImageModal(Modal, title="Imagen del embed"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        data = load_json("welcome.json").get(guild_id, {})
        self.image = TextInput(
            label="URL de la imagen (vacío para quitar)",
            default=data.get("image", ""),
            required=False,
            max_length=500
        )
        self.add_item(self.image)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_json("welcome.json")
        if self.guild_id not in data:
            data[self.guild_id] = {}
        data[self.guild_id]["image"] = self.image.value or None
        save_json("welcome.json", data)
        await interaction.response.send_message("Imagen actualizada.", ephemeral=True)


async def send_welcome(member, guild):
    data = load_json("welcome.json").get(str(guild.id), {})
    if not data.get("channel_id"):
        return

    channel = guild.get_channel(int(data["channel_id"]))
    if not channel:
        return

    try:
        color_int = int(data.get("color", "#00ff00").replace("#", ""), 16)
    except:
        color_int = 0x00ff00

    message = data.get("message", "¡Bienvenido {user} a **{server}**!")
    message = (message
               .replace("{user}", member.mention)
               .replace("{server}", guild.name)
               .replace("{count}", str(guild.member_count)))

    embed = discord.Embed(
        title=data.get("title", "¡Bienvenido!"),
        description=message,
        color=color_int,
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    if data.get("image"):
        embed.set_image(url=data["image"])

    recommended = data.get("recommended", [])
    if recommended:
        lista = "\n".join([f"• <#{cid}>" for cid in recommended])
        embed.add_field(name="Canales recomendados", value=lista, inline=False)

    await channel.send(embed=embed)


@bot.event
async def on_member_join(member):
    await send_welcome(member, member.guild)


@tree.command(name="welcome-setup", description="Configura el sistema de bienvenidas")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    data = load_json("welcome.json").get(guild_id, {})

    embed = discord.Embed(title="⚙️ Panel de Bienvenidas", description="Usa los botones para configurar todo.", color=0x5865F2)
    embed.add_field(name="Canal", value=f"<#{data['channel_id']}>" if data.get("channel_id") else "No configurado", inline=True)
    embed.add_field(name="Color", value=data.get("color", "#00ff00"), inline=True)
    embed.add_field(name="Título", value=data.get("title", "¡Bienvenido!"), inline=True)
    embed.add_field(name="Mensaje", value=data.get("message", "¡Bienvenido {user} a **{server}**!"), inline=False)
    embed.add_field(name="Imagen", value=data.get("image") or "Ninguna", inline=False)
    rec = data.get("recommended", [])
    embed.add_field(name="Canales recomendados", value=", ".join([f"<#{c}>" for c in rec]) if rec else "Ninguno", inline=False)

    await interaction.response.send_message(embed=embed, view=WelcomePanel(interaction.guild.id), ephemeral=True)


# ====================== COMANDOS DE MODERACIÓN ======================

@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx, channel: discord.TextChannel = None, tiempo: str = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    msg = f"🔒 Canal {channel.mention} bloqueado."
    if tiempo:
        msg += f" (durante {tiempo})"
    await ctx.send(msg)


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send(f"🔓 Canal {channel.mention} desbloqueado.")


@bot.command(name="warn")
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, motivo: str = "Sin motivo"):
    data = load_json("warns.json")
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)

    if guild_id not in data:
        data[guild_id] = {}
    if user_id not in data[guild_id]:
        data[guild_id][user_id] = []

    data[guild_id][user_id].append({
        "motivo": motivo,
        "moderator": str(ctx.author.id),
        "fecha": datetime.utcnow().isoformat()
    })
    save_json("warns.json", data)

    embed = discord.Embed(title="⚠️ Usuario advertido", color=0xffaa00, timestamp=datetime.utcnow())
    embed.add_field(name="Usuario", value=member.mention, inline=True)
    embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)
    embed.add_field(name="Total warns", value=str(len(data[guild_id][user_id])), inline=True)
    await ctx.send(embed=embed)


@bot.command(name="warns")
@commands.has_permissions(moderate_members=True)
async def warns(ctx, member: discord.Member):
    data = load_json("warns.json")
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    warns_list = data.get(guild_id, {}).get(user_id, [])

    if not warns_list:
        return await ctx.send(f"{member.mention} no tiene advertencias.")

    embed = discord.Embed(title=f"Advertencias de {member}", color=0xffaa00, timestamp=datetime.utcnow())
    for i, w in enumerate(warns_list, 1):
        embed.add_field(
            name=f"#{i} - {w['fecha'][:10]}",
            value=f"**Motivo:** {w['motivo']}\n**Mod:** <@{w['moderator']}>",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, motivo: str = "Sin motivo"):
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("No puedes expulsar a alguien con un rol igual o superior al tuyo.")
    await member.kick(reason=motivo)
    embed = discord.Embed(title="👢 Usuario expulsado", color=0xff5500, timestamp=datetime.utcnow())
    embed.add_field(name="Usuario", value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, motivo: str = "Sin motivo"):
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("No puedes banear a alguien con un rol igual o superior al tuyo.")
    await member.ban(reason=motivo)
    embed = discord.Embed(title="🔨 Usuario baneado", color=0xff0000, timestamp=datetime.utcnow())
    embed.add_field(name="Usuario", value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Usuario **{user}** desbaneado.")
    except:
        await ctx.send("No se pudo desbanear. Verifica que el ID sea correcto y que el usuario esté baneado.")


@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, tiempo: str, *, motivo: str = "Sin motivo"):
    delta = parse_time(tiempo)
    if not delta:
        return await ctx.send("Formato de tiempo inválido. Usa por ejemplo: `10m`, `1h`, `2d`, `30s`")
    if delta > timedelta(days=28):
        return await ctx.send("El máximo de timeout es 28 días.")

    await member.timeout(delta, reason=motivo)
    embed = discord.Embed(title="🔇 Usuario silenciado", color=0x999999, timestamp=datetime.utcnow())
    embed.add_field(name="Usuario", value=member.mention, inline=True)
    embed.add_field(name="Duración", value=tiempo, inline=True)
    embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 Se le ha quitado el silencio a {member.mention}.")


@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear(ctx, cantidad: int = 10):
    if cantidad < 1 or cantidad > 100:
        return await ctx.send("La cantidad debe estar entre 1 y 100.")
    deleted = await ctx.channel.purge(limit=cantidad + 1)
    msg = await ctx.send(f"🧹 Se eliminaron **{len(deleted)-1}** mensajes.")
    await msg.delete(delay=3)


@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, segundos: int = 0):
    if segundos < 0 or segundos > 21600:
        return await ctx.send("El valor debe estar entre 0 y 21600 segundos (6 horas).")
    await ctx.channel.edit(slowmode_delay=segundos)
    if segundos == 0:
        await ctx.send("🐢 Modo lento desactivado.")
    else:
        await ctx.send(f"🐢 Modo lento activado: **{segundos}** segundos.")


@bot.command(name="nick")
@commands.has_permissions(manage_nicknames=True)
async def nick(ctx, member: discord.Member, *, nuevo_nick: str = None):
    try:
        await member.edit(nick=nuevo_nick)
        if nuevo_nick:
            await ctx.send(f"Apodo de {member.mention} cambiado a **{nuevo_nick}**.")
        else:
            await ctx.send(f"Apodo de {member.mention} restablecido.")
    except discord.Forbidden:
        await ctx.send("No tengo permisos para cambiar el apodo de ese usuario.")


@bot.command(name="cmds")
async def cmds(ctx):
    embed = discord.Embed(
        title="📜 Lista de comandos",
        description="Prefijo: `?`",
        color=0x5865F2,
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="🛡️ Moderación",
        value=(
            "`?lock [#canal] [tiempo]` - Bloquea un canal\n"
            "`?unlock [#canal]` - Desbloquea un canal\n"
            "`?warn @usuario [motivo]` - Advierte a un usuario\n"
            "`?warns @usuario` - Ver advertencias\n"
            "`?kick @usuario [motivo]` - Expulsa\n"
            "`?ban @usuario [motivo]` - Banea\n"
            "`?unban ID` - Desbanea\n"
            "`?mute @usuario 10m [motivo]` - Silencia (timeout)\n"
            "`?unmute @usuario` - Quita el silencio\n"
            "`?clear [cantidad]` - Borra mensajes (1-100)\n"
            "`?slowmode [segundos]` - Activa modo lento\n"
            "`?nick @usuario [nuevo]` - Cambia apodo"    
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ Configuración (Slash)",
        value=(
            "`/welcome-setup` - Configurar sistema de bienvenidas\n"
            "`/config-automod` - Configurar AutoMod y canal de logs"
            "`/tickets-setup` - Configurar sistema de tickets"
        ),
        inline=False
    )
    embed.set_footer(text=f"Solicitado por {ctx.author}")
    await ctx.send(embed=embed)


# ====================== EVENTOS ======================
@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Slash commands sincronizados: {len(synced)}")
    except Exception as e:
        print(e)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ Permisos insuficientes",
            description="No tienes los permisos necesarios para usar este comando.",
            color=0xff0000
        )
        return await ctx.send(embed=embed, delete_after=8)

    if isinstance(error, commands.MemberNotFound):
        embed = discord.Embed(
            title="❌ Usuario no encontrado",
            description="No pude encontrar a ese usuario. Menciona correctamente o usa su ID.",
            color=0xff0000
        )
        return await ctx.send(embed=embed, delete_after=8)

    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        ayudas = {
            "warn": {
                "uso": "`?warn @usuario [motivo]`",
                "ejemplo": "`?warn @Neiwito Insultos`",
                "desc": "Advierte a un usuario y guarda el registro."
            },
            "warns": {
                "uso": "`?warns @usuario`",
                "ejemplo": "`?warns @Neiwito`",
                "desc": "Muestra todas las advertencias de un usuario."
            },
            "kick": {
                "uso": "`?kick @usuario [motivo]`",
                "ejemplo": "`?kick @Neiwito Spam`",
                "desc": "Expulsa a un usuario del servidor."
            },
            "ban": {
                "uso": "`?ban @usuario [motivo]`",
                "ejemplo": "`?ban @Neiwito Toxicidad`",
                "desc": "Banea a un usuario del servidor."
            },
            "unban": {
                "uso": "`?unban ID`",
                "ejemplo": "`?unban 123456789012345678`",
                "desc": "Desbanea a un usuario usando su ID."
            },
            "mute": {
                "uso": "`?mute @usuario 10m [motivo]`",
                "ejemplo": "`?mute @Neiwito 1h Flood`",
                "desc": "Silencia a un usuario (timeout). Formatos: `30s`, `10m`, `2h`, `1d`"
            },
            "unmute": {
                "uso": "`?unmute @usuario`",
                "ejemplo": "`?unmute @Neiwito`",
                "desc": "Quita el silencio a un usuario."
            },
            "clear": {
                "uso": "`?clear [cantidad]`",
                "ejemplo": "`?clear 25`",
                "desc": "Elimina mensajes del canal (máximo 100)."
            },
            "lock": {
                "uso": "`?lock [#canal] [tiempo]`",
                "ejemplo": "`?lock #general 10m`",
                "desc": "Bloquea un canal para que nadie pueda escribir."
            },
            "unlock": {
                "uso": "`?unlock [#canal]`",
                "ejemplo": "`?unlock #general`",
                "desc": "Desbloquea un canal."
            },
            "slowmode": {
                "uso": "`?slowmode [segundos]`",
                "ejemplo": "`?slowmode 5`",
                "desc": "Activa el modo lento (0 para desactivar)."
            },
            "nick": {
                "uso": "`?nick @usuario [nuevo apodo]`",
                "ejemplo": "`?nick @Neiwito Admin`",
                "desc": "Cambia el apodo de un usuario."
            }
        }

        cmd = ctx.command.name if ctx.command else "desconocido"
        info = ayudas.get(cmd)

        if info:
            embed = discord.Embed(
                title=f"📖 Uso del comando `?{cmd}`",
                color=0x5865F2
            )
            embed.add_field(name="Uso correcto", value=info["uso"], inline=False)
            embed.add_field(name="Ejemplo", value=info["ejemplo"], inline=False)
            embed.add_field(name="Descripción", value=info["desc"], inline=False)
        else:
            embed = discord.Embed(
                title="❌ Argumentos incorrectos",
                description="Revisa cómo se usa el comando con `?cmds`.",
                color=0xff0000
            )

        return await ctx.send(embed=embed, delete_after=15)

    print(f"Error en comando: {error}")


# ====================== KEEP ALIVE (Render + UptimeRobot) ======================
app = Flask("")

@app.route("/")
def home():
    return "Bot online"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()


# ====================== CARGA DE EXTENSIONES + INICIO ======================
async def main():
    async with bot:
        await bot.load_extension("actividad")
        await bot.load_extension("automod")
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
