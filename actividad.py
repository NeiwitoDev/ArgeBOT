import discord
from discord.ext import commands, tasks
from itertools import cycle

# ====================== CONFIGURACIÓN ======================
INTERVALO_SEGUNDOS = 10          

ESTADOS = [
    "↪ Developer: Neiwito!",
    "↪ Code: ArgRp"
]
# ==========================================================

class Actividad(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.estados = cycle(ESTADOS)
        self.cambiar_estado.start()

    def cog_unload(self):
        self.cambiar_estado.cancel()

    @tasks.loop(seconds=INTERVALO_SEGUNDOS)
    async def cambiar_estado(self):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=next(self.estados)
            ),
            status=discord.Status.online
        )

    @cambiar_estado.before_loop
    async def before_cambiar_estado(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Actividad(bot))
