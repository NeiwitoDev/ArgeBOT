import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput, ChannelSelect, RoleSelect
from datetime import datetime
import json
import os
import io
import asyncio

# ====================== BASE DE DATOS ======================
def load_data():
    if not os.path.exists("tickets.json"):
        return {}
    with open("tickets.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open("tickets.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_guild_config(guild_id: str):
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {
            "panel_title": "🎫 Sistema de Tickets",
            "panel_message": "¿Necesitas ayuda?\nHaz clic en el botón de abajo para crear un ticket privado.",
            "panel_color": "#5865F2",
            "mode": "buttons",          # buttons o menu
            "naming": "number",         # number o user
            "counter": 1,
            "welcome_message": "Hola {user}, gracias por contactarnos.\nUn miembro del staff te atenderá pronto.\n\n**Categoría:** {category}",
            "categories": {
                "soporte": {"label": "Soporte", "emoji": "🛠️", "description": "Ayuda general"},
                "reporte": {"label": "Reporte", "emoji": "🚨", "description": "Reportar a un usuario"},
                "dudas": {"label": "Dudas", "emoji": "❓", "description": "Preguntas del servidor"}
            },
            "staff_role": None,
            "log_channel": None,
            "category_id": None
        }
        save_data(data)
    return data[guild_id]

# ====================== VISTAS DEL PANEL DE CREACIÓN ======================
class TicketPanelView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        config = get_guild_config(guild_id)

        if config["mode"] == "buttons":
            # Crear un botón por cada categoría
            for key, cat in config["categories"].items():
                button = Button(
                    label=cat["label"],
                    emoji=cat.get("emoji"),
                    style=discord.ButtonStyle.primary,
                    custom_id=f"ticket_btn_{key}"
                )
                button.callback = self.make_callback(key)
                self.add_item(button)
        else:
            # Modo menú
            options = []
            for key, cat in config["categories"].items():
                options.append(discord.SelectOption(
                    label=cat["label"],
                    description=cat.get("description", ""),
                    emoji=cat.get("emoji"),
                    value=key
                ))
            select = Select(placeholder="Selecciona una categoría...", options=options, custom_id="ticket_select")
            select.callback = self.select_callback
            self.add_item(select)

    def make_callback(self, category_key):
        async def callback(interaction: discord.Interaction):
            await self.create_ticket(interaction, category_key)
        return callback

    async def select_callback(self, interaction: discord.Interaction):
        category_key = self.children[0].values[0]
        await self.create_ticket(interaction, category_key)

    async def create_ticket(self, interaction: discord.Interaction, category_key: str):
        config = get_guild_config(str(interaction.guild.id))

        # Verificar si ya tiene ticket abierto
        for ch in interaction.guild.text_channels:
            if ch.topic and f"userid:{interaction.user.id}" in ch.topic:
                return await interaction.response.send_message(
                    f"Ya tienes un ticket abierto: {ch.mention}", ephemeral=True
                )

        if not config.get("category_id") or not config.get("staff_role"):
            return await interaction.response.send_message(
                "El sistema de tickets no está completamente configurado.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        category = interaction.guild.get_channel(int(config["category_id"]))
        staff_role = interaction.guild.get_role(int(config["staff_role"]))
        cat_info = config["categories"].get(category_key, {"label": category_key})

        # Nombre del canal
        if config["naming"] == "number":
            number = config.get("counter", 1)
            channel_name = f"ticket-{number:03d}"
            config["counter"] = number + 1
            # Guardar contador
            data = load_data()
            data[str(interaction.guild.id)] = config
            save_data(data)
        else:
            channel_name = f"ticket-{interaction.user.name}".lower().replace(" ", "-")[:40]

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)

        try:
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"userid:{interaction.user.id}|category:{category_key}|claimed:None"
            )
        except Exception as e:
            return await interaction.followup.send(f"Error al crear el ticket: {e}", ephemeral=True)

        # Mensaje de bienvenida
        welcome = config.get("welcome_message", "Hola {user}")
        welcome = welcome.replace("{user}", interaction.user.mention).replace("{category}", cat_info["label"])

        embed = discord.Embed(
            title=f"Ticket • {cat_info['label']}",
            description=welcome,
            color=int(config.get("panel_color", "#5865F2").replace("#", ""), 16),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"ID: {interaction.user.id}")

        await ticket_channel.send(
            content=f"{interaction.user.mention} {staff_role.mention if staff_role else ''}",
            embed=embed,
            view=TicketControlView()
        )

        await interaction.followup.send(f"✅ Ticket creado: {ticket_channel.mention}", ephemeral=True)
        await send_log(interaction.guild, "Ticket creado", interaction.user, ticket_channel, cat_info["label"])


# ====================== CONTROLES DENTRO DEL TICKET ======================
class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    def is_staff(self, interaction: discord.Interaction) -> bool:
        config = get_guild_config(str(interaction.guild.id))
        staff_id = config.get("staff_role")
        if not staff_id:
            return interaction.user.guild_permissions.manage_channels
        role = interaction.guild.get_role(int(staff_id))
        return role in interaction.user.roles or interaction.user.guild_permissions.administrator

    @discord.ui.button(label="🔒 Cerrar", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction) and not interaction.channel.topic.startswith(f"userid:{interaction.user.id}"):
            return await interaction.response.send_message("No tienes permiso para cerrar este ticket.", ephemeral=True)
        await interaction.response.send_modal(CloseConfirmModal())

    @discord.ui.button(label="👋 Reclamar", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("Solo el staff puede reclamar tickets.", ephemeral=True)

        topic = interaction.channel.topic or ""
        if "claimed:" in topic and "claimed:None" not in topic:
            return await interaction.response.send_message("Este ticket ya está reclamado.", ephemeral=True)

        new_topic = topic.replace("claimed:None", f"claimed:{interaction.user.id}")
        await interaction.channel.edit(topic=new_topic)

        embed = discord.Embed(description=f"Ticket reclamado por {interaction.user.mention}", color=0x57F287)
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="↩️ Quitar reclamo", style=discord.ButtonStyle.secondary, custom_id="ticket_unclaim")
    async def unclaim(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("Solo el staff puede hacer esto.", ephemeral=True)

        topic = interaction.channel.topic or ""
        if "claimed:None" in topic:
            return await interaction.response.send_message("Este ticket no está reclamado.", ephemeral=True)

        # Extraer el ID reclamado
        import re
        match = re.search(r"claimed:(\d+)", topic)
        if match and str(interaction.user.id) != match.group(1) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Solo quien lo reclamó o un administrador puede quitar el reclamo.", ephemeral=True)

        new_topic = re.sub(r"claimed:\d+", "claimed:None", topic)
        await interaction.channel.edit(topic=new_topic)

        embed = discord.Embed(description=f"Reclamo eliminado por {interaction.user.mention}", color=0xFEE75C)
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="➕ Añadir", style=discord.ButtonStyle.success, custom_id="ticket_add")
    async def add_user(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("Solo el staff puede añadir usuarios.", ephemeral=True)
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="➖ Eliminar", style=discord.ButtonStyle.secondary, custom_id="ticket_remove")
    async def remove_user(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("Solo el staff puede eliminar usuarios.", ephemeral=True)
        await interaction.response.send_modal(RemoveUserModal())


class CloseConfirmModal(Modal, title="Cerrar Ticket"):
    def __init__(self):
        super().__init__()
        self.reason = TextInput(label="Motivo del cierre", style=discord.TextStyle.paragraph, required=False, max_length=500, placeholder="Ej: Problema resuelto")
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 Cerrando ticket en 5 segundos...", ephemeral=True)

        # Transcript
        lines = []
        async for msg in interaction.channel.history(limit=150, oldest_first=True):
            time = msg.created_at.strftime("%Y-%m-%d %H:%M")
            content = msg.content or "[embed/archivo/sticker]"
            lines.append(f"[{time}] {msg.author}: {content}")

        transcript = "\n".join(lines) or "Sin mensajes."
        file = discord.File(fp=io.StringIO(transcript), filename=f"transcript-{interaction.channel.name}.txt")

        await send_log(
            interaction.guild,
            "Ticket cerrado",
            interaction.user,
            interaction.channel,
            reason=self.reason.value or "Sin motivo",
            file=file
        )

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Cerrado por {interaction.user}")
        except:
            pass


class AddUserModal(Modal, title="Añadir usuario"):
    def __init__(self):
        super().__init__()
        self.user_id = TextInput(label="ID del usuario", required=True, max_length=20)
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            member = await interaction.guild.fetch_member(int(self.user_id.value))
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, attach_files=True)
            await interaction.response.send_message(f"✅ {member.mention} añadido al ticket.")
        except:
            await interaction.response.send_message("❌ No se pudo añadir. Verifica el ID.", ephemeral=True)


class RemoveUserModal(Modal, title="Eliminar usuario"):
    def __init__(self):
        super().__init__()
        self.user_id = TextInput(label="ID del usuario", required=True, max_length=20)
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            member = await interaction.guild.fetch_member(int(self.user_id.value))
            await interaction.channel.set_permissions(member, overwrite=None)
            await interaction.response.send_message(f"✅ {member.mention} eliminado del ticket.")
        except:
            await interaction.response.send_message("❌ No se pudo eliminar. Verifica el ID.", ephemeral=True)


# ====================== PANEL DE CONFIGURACIÓN /tickets-setup ======================
class TicketsSetupPanel(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Título Panel", style=discord.ButtonStyle.primary, row=0)
    async def set_title(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TitleModal(self.guild_id))

    @discord.ui.button(label="Mensaje Panel", style=discord.ButtonStyle.primary, row=0)
    async def set_message(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MessageModal(self.guild_id))

    @discord.ui.button(label="Color", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ColorModal(self.guild_id))

    @discord.ui.button(label="Modo (Botones/Menú)", style=discord.ButtonStyle.secondary, row=1)
    async def set_mode(self, interaction: discord.Interaction, button: Button):
        config = get_guild_config(self.guild_id)
        new_mode = "menu" if config["mode"] == "buttons" else "buttons"
        data = load_data()
        data[self.guild_id]["mode"] = new_mode
        save_data(data)
        await interaction.response.send_message(f"Modo cambiado a: **{new_mode}**", ephemeral=True)

    @discord.ui.button(label="Nombre (Número/Usuario)", style=discord.ButtonStyle.secondary, row=1)
    async def set_naming(self, interaction: discord.Interaction, button: Button):
        config = get_guild_config(self.guild_id)
        new_naming = "user" if config["naming"] == "number" else "number"
        data = load_data()
        data[self.guild_id]["naming"] = new_naming
        save_data(data)
        await interaction.response.send_message(
            f"Estilo de nombre cambiado a: **{'ticket-001' if new_naming == 'number' else 'ticket-usuario'}**",
            ephemeral=True
        )

    @discord.ui.button(label="Mensaje Bienvenida", style=discord.ButtonStyle.secondary, row=1)
    async def set_welcome(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WelcomeModal(self.guild_id))

    @discord.ui.button(label="Categoría Discord", style=discord.ButtonStyle.primary, row=2)
    async def set_category(self, interaction: discord.Interaction, button: Button):
        view = ChannelSelectView(self.guild_id, "category")
        await interaction.response.send_message("Selecciona la categoría de Discord:", view=view, ephemeral=True)

    @discord.ui.button(label="Rol Staff", style=discord.ButtonStyle.primary, row=2)
    async def set_staff(self, interaction: discord.Interaction, button: Button):
        view = RoleSelectView(self.guild_id)
        await interaction.response.send_message("Selecciona el rol de staff:", view=view, ephemeral=True)

    @discord.ui.button(label="Canal Logs", style=discord.ButtonStyle.primary, row=2)
    async def set_logs(self, interaction: discord.Interaction, button: Button):
        view = ChannelSelectView(self.guild_id, "logs")
        await interaction.response.send_message("Selecciona el canal de logs:", view=view, ephemeral=True)

    @discord.ui.button(label="Enviar Panel", style=discord.ButtonStyle.success, row=3)
    async def send_panel(self, interaction: discord.Interaction, button: Button):
        config = get_guild_config(self.guild_id)
        if not config.get("category_id") or not config.get("staff_role"):
            return await interaction.response.send_message(
                "Primero configura la **Categoría de Discord** y el **Rol Staff**.", ephemeral=True
            )

        color = int(config.get("panel_color", "#5865F2").replace("#", ""), 16)
        embed = discord.Embed(
            title=config.get("panel_title", "🎫 Sistema de Tickets"),
            description=config.get("panel_message", "Haz clic para crear un ticket."),
            color=color
        )
        embed.set_footer(text="ArgeBOT • Sistema de Tickets")

        await interaction.channel.send(embed=embed, view=TicketPanelView(self.guild_id))
        await interaction.response.send_message("✅ Panel enviado correctamente.", ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=3)
    async def reset(self, interaction: discord.Interaction, button: Button):
        data = load_data()
        if self.guild_id in data:
            del data[self.guild_id]
            save_data(data)
        await interaction.response.send_message("Configuración de tickets reiniciada.", ephemeral=True)


# ====================== MODALS DE CONFIGURACIÓN ======================
class TitleModal(Modal, title="Título del Panel"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        config = get_guild_config(guild_id)
        self.input = TextInput(label="Título", default=config.get("panel_title", ""), max_length=256)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        data[self.guild_id]["panel_title"] = self.input.value
        save_data(data)
        await interaction.response.send_message("Título actualizado.", ephemeral=True)


class MessageModal(Modal, title="Mensaje del Panel"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        config = get_guild_config(guild_id)
        self.input = TextInput(label="Mensaje", style=discord.TextStyle.paragraph, default=config.get("panel_message", ""), max_length=2000)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        data[self.guild_id]["panel_message"] = self.input.value
        save_data(data)
        await interaction.response.send_message("Mensaje actualizado.", ephemeral=True)


class ColorModal(Modal, title="Color del Embed"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        config = get_guild_config(guild_id)
        self.input = TextInput(label="Color HEX", default=config.get("panel_color", "#5865F2"), max_length=7)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        data[self.guild_id]["panel_color"] = self.input.value
        save_data(data)
        await interaction.response.send_message("Color actualizado.", ephemeral=True)


class WelcomeModal(Modal, title="Mensaje de Bienvenida del Ticket"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        config = get_guild_config(guild_id)
        self.input = TextInput(
            label="Mensaje (usa {user} y {category})",
            style=discord.TextStyle.paragraph,
            default=config.get("welcome_message", ""),
            max_length=2000
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        data[self.guild_id]["welcome_message"] = self.input.value
        save_data(data)
        await interaction.response.send_message("Mensaje de bienvenida actualizado.", ephemeral=True)


class ChannelSelectView(View):
    def __init__(self, guild_id, mode):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.mode = mode
        channel_types = [discord.ChannelType.category] if mode == "category" else [discord.ChannelType.text]
        select = ChannelSelect(placeholder="Selecciona...", channel_types=channel_types, max_values=1)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        if self.guild_id not in data:
            get_guild_config(self.guild_id)
            data = load_data()
        selected = str(self.children[0].values[0].id)
        if self.mode == "category":
            data[self.guild_id]["category_id"] = selected
        else:
            data[self.guild_id]["log_channel"] = selected
        save_data(data)
        await interaction.response.edit_message(content=f"Configurado: <#{selected}>", view=None)


class RoleSelectView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        select = RoleSelect(placeholder="Selecciona el rol staff", max_values=1)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        if self.guild_id not in data:
            get_guild_config(self.guild_id)
            data = load_data()
        selected = str(self.children[0].values[0].id)
        data[self.guild_id]["staff_role"] = selected
        save_data(data)
        await interaction.response.edit_message(content=f"Rol staff: <@&{selected}>", view=None)


async def send_log(guild, action, user, channel, category=None, reason=None, file=None):
    config = get_guild_config(str(guild.id))
    log_id = config.get("log_channel")
    if not log_id:
        return
    log_channel = guild.get_channel(int(log_id))
    if not log_channel:
        return

    embed = discord.Embed(title=f"🎫 {action}", color=0x5865F2, timestamp=datetime.utcnow())
    embed.add_field(name="Usuario", value=f"{user} (`{user.id}`)", inline=True)
    embed.add_field(name="Canal", value=getattr(channel, "name", str(channel)), inline=True)
    if category:
        embed.add_field(name="Categoría", value=category, inline=True)
    if reason:
        embed.add_field(name="Motivo", value=reason, inline=False)

    await log_channel.send(embed=embed, file=file)


# ====================== COG ======================
class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketControlView())

    @app_commands.command(name="tickets-setup", description="Configura el sistema de tickets profesional")
    @app_commands.checks.has_permissions(administrator=True)
    async def tickets_setup(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        config = get_guild_config(guild_id)

        embed = discord.Embed(
            title="⚙️ Panel de Configuración de Tickets",
            description="Configura completamente el sistema de tickets.",
            color=0x5865F2
        )
        embed.add_field(name="Título", value=config.get("panel_title", "—"), inline=True)
        embed.add_field(name="Color", value=config.get("panel_color", "#5865F2"), inline=True)
        embed.add_field(name="Modo", value=config.get("mode", "buttons"), inline=True)
        embed.add_field(name="Nombre", value="ticket-001" if config.get("naming") == "number" else "ticket-usuario", inline=True)
        embed.add_field(name="Categoría Discord", value=f"<#{config['category_id']}>" if config.get("category_id") else "No configurada", inline=True)
        embed.add_field(name="Rol Staff", value=f"<@&{config['staff_role']}>" if config.get("staff_role") else "No configurado", inline=True)
        embed.add_field(name="Canal Logs", value=f"<#{config['log_channel']}>" if config.get("log_channel") else "No configurado", inline=True)

        await interaction.response.send_message(embed=embed, view=TicketsSetupPanel(guild_id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
