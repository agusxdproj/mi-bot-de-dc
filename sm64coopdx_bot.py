import asyncio
import discord
from discord.ext import commands, tasks
import logging
import traceback
from config import BOT_TOKEN, COMMAND_PREFIX, setup_logging, MAX_SESSION_DURATION_HOURS, SESSION_WARNING_THRESHOLD_HOURS
from session_manager import SessionManager
from utils import format_duration, format_timestamp, is_long_session

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Bot setup
intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
session_manager = SessionManager()

@bot.event
async def on_ready():
    """Event fired when bot is ready."""
    logger.info(f"✅ Bot connected as {bot.user}")
    logger.info(f"🔒 Connected to {len(bot.guilds)} servers")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"🔄 Synced {len(synced)} slash commands")
        logger.info(f"📓 Available commands: {[cmd.name for cmd in synced]}")
    except Exception as e:
        logger.error(f"❌ Error syncing commands: {e}")
        logger.error(traceback.format_exc())
    
    # Start background tasks
    cleanup_sessions.start()
    session_warnings.start()
    
    logger.info("🎮 SM64 Co-op DX Bot is ready! Use /play to start a gaming session")

@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Handle application command errors."""
    logger.error(f"Command error in {interaction.command.name if interaction.command else 'unknown'}: {error}")
    
    if not interaction.response.is_done():
        await interaction.response.send_message(
            f"❌ An error occurred: {str(error)}", 
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"❌ An error occurred: {str(error)}", 
            ephemeral=True
        )

@bot.tree.command(name="play", description="Iniciar o unirse a una sesión de SM64 Co-op DX")
@discord.app_commands.describe(
    usuario="Mencionar un usuario para ver sus estadísticas",
    contraseña="Contraseña opcional para la sesión"
)
async def play(interaction: discord.Interaction, contraseña: str = "", usuario: discord.User = None):
    """Start or join a gaming session."""
    try:
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        if usuario:
            active_sessions = session_manager.get_all_active_sessions()
            user_session = None
            
            for session in active_sessions:
                if session.host_user_id == usuario.id:
                    user_session = session
                    break
            
            embed = discord.Embed(
                title=f"📊 Estadísticas de {usuario.display_name}",
                description="Información de sesión del usuario",
                color=0x9932cc
            )
            
            if user_session:
                duration = format_duration(user_session.get_duration())
                password_info = f"Contraseña: {user_session.password}" if user_session.password else "Sin contraseña"
                
                embed.add_field(
                    name="🎮 Estado",
                    value="En sesión activa",
                    inline=True
                )
                
                embed.add_field(
                    name="⏰ Duración",
                    value=duration,
                    inline=True
                )
                
                embed.add_field(
                    name="🔑 Acceso",
                    value=password_info,
                    inline=True
                )
            else:
                embed.add_field(
                    name="🎮 Estado",
                    value="No está en una sesión activa",
                    inline=False
                )
            
            embed.set_footer(text="Estadísticas del usuario")
            await interaction.response.send_message(embed=embed)
            return
        
        password_to_use = contraseña if contraseña.strip() else None
        session = session_manager.start_session(guild_id, channel_id, user_id, username, password_to_use)
        
        embed = discord.Embed(
            title="🎮 SM64 Co-op DX Session",
            description="¡La sesión de juego está activa! (es posible que el tiempo no sea exacto)",
            color=0x00ff00,
            timestamp=session.start_time
        )
        
        embed.add_field(
            name="👑 Anfitrión",
            value=session.host_username,
            inline=True
        )
        
        embed.add_field(
            name="⏰ Iniciado",
            value=f"<t:{int(session.start_time.timestamp())}:R>",
            inline=True
        )
        
        if password_to_use:
            embed.add_field(
                name="🔑 Contraseña",
                value=password_to_use,
                inline=True
            )
        
        embed.set_footer(text="/stop para terminar la sesión")
        
        await interaction.response.send_message(embed=embed)
        
        logger.info(f"Play command executed by {username} in guild {guild_id}")
        
    except Exception as e:
        logger.error(f"Error in play command: {e}")
        logger.error(traceback.format_exc())
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Error al iniciar la sesión. Inténtalo de nuevo.", 
                ephemeral=True
            )
        else:
            await interaction.edit_original_response(
                content="❌ Error al iniciar la sesión. Inténtalo de nuevo."
            )

@bot.tree.command(name="session", description="Show current session information and time tracking")
async def session_info(interaction: discord.Interaction):
    """Display current session information."""
    try:
        guild_id = interaction.guild.id
        session = session_manager.get_session(guild_id)
        
        if not session or not session.is_active:
            embed = discord.Embed(
                title="ℹ️ No Active Session",
                description="There's no active gaming session in this server.\nUse `/play` to start one!",
                color=0x808080
            )
            await interaction.response.send_message(embed=embed)
            return
        
        duration = session.get_duration()
        participant_count = session.get_participant_count()
        
        embed = discord.Embed(
            title="📊 Current Session Status",
            description="SM64 Co-op DX Session Information",
            color=0x00bfff,
            timestamp=session.start_time
        )
        
        embed.add_field(
            name="👑 Session Host",
            value=session.host_username,
            inline=True
        )
        
        embed.add_field(
            name="🗣️ Total Players",
            value=str(participant_count),
            inline=True
        )
        
        embed.add_field(
            name="⏰ Duration",
            value=format_duration(duration),
            inline=True
        )
        
        embed.add_field(
            name="🕐 Started At",
            value=f"<t:{int(session.start_time.timestamp())}:F>",
            inline=True
        )
        
        embed.add_field(
            name="📍 Channel",
            value=f"<#{session.channel_id}>",
            inline=True
        )
        
        if is_long_session(duration, SESSION_WARNING_THRESHOLD_HOURS):
            embed.add_field(
                name="⚠️ Long Session Alert",
                value=f"Session has been running for over {SESSION_WARNING_THRESHOLD_HOURS} hours. Consider taking a break!",
                inline=False
            )
        
        embed.set_footer(text="Session time is tracked automatically • Use /stop to end")
        
        await interaction.response.send_message(embed=embed)
        
        logger.info(f"Session info requested by {interaction.user.display_name} in guild {guild_id}")
        
    except Exception as e:
        logger.error(f"Error in session command: {e}")
        logger.error(traceback.format_exc())
        await interaction.response.send_message(
            "❌ Failed to retrieve session information.", 
            ephemeral=True
        )

@bot.tree.command(name="stop", description="Finalizar la sesión de juego actual")
async def stop_session(interaction: discord.Interaction):
    """End the current gaming session."""
    try:
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        session = session_manager.get_session(guild_id)
        
        if not session or not session.is_active:
            embed = discord.Embed(
                title="ℹ️ Sin Sesión Activa",
                description="No hay una sesión activa para detener en este servidor.",
                color=0x808080
            )
            await interaction.response.send_message(embed=embed)
            return
        
        is_host = session.host_user_id == user_id
        
        if not is_host:
            embed = discord.Embed(
                title="🚫 Acceso Denegado",
                description="Solo el anfitrión de la sesión puede finalizarla.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        final_duration = session.get_duration()
        participant_count = session.get_participant_count()
        
        session_manager.end_session(guild_id)
        
        embed = discord.Embed(
            title="🛑 Sesión Finalizada",
            description="¡La sesión de SM64 Co-op DX ha terminado!",
            color=0xff4500,
            timestamp=session.end_time
        )
        
        embed.add_field(
            name="👑 Anfitrión",
            value=session.host_username,
            inline=True
        )
        
        embed.add_field(
            name="⏰ Duración Total",
            value=format_duration(final_duration),
            inline=True
        )
        
        embed.add_field(
            name="🕐 Período de Sesión",
            value=f"<t:{int(session.start_time.timestamp())}:t> - <t:{int(session.end_time.timestamp())}:t>",
            inline=False
        )
        
        if final_duration >= 3600:
            embed.add_field(
                name="🏆 ¡Excelente Sesión!",
                value="¡Gracias por la sesión de juego extendida!",
                inline=False
            )
        
        embed.set_footer(text="Sesión finalizada por " + interaction.user.display_name)
        
        await interaction.response.send_message(embed=embed)
        
        await asyncio.sleep(300)
        session_manager.remove_session(guild_id)
        
        logger.info(f"Session stopped by {interaction.user.display_name} in guild {guild_id}")
        
    except Exception as e:
        logger.error(f"Error in stop command: {e}")
        logger.error(traceback.format_exc())
        await interaction.response.send_message(
            "❌ Failed to stop session. Please try again.", 
            ephemeral=True
        )

@tasks.loop(hours=1)
async def cleanup_sessions():
    """Periodic cleanup of old sessions."""
    try:
        cleaned = session_manager.cleanup_old_sessions()
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old sessions")
    except Exception as e:
        logger.error(f"Error in session cleanup: {e}")

@tasks.loop(hours=2)
async def session_warnings():
    """Check for long-running sessions and send warnings."""
    try:
        active_sessions = session_manager.get_all_active_sessions()
        
        for session in active_sessions:
            duration = session.get_duration()
            
            if is_long_session(duration, SESSION_WARNING_THRESHOLD_HOURS):
                try:
                    channel = bot.get_channel(session.channel_id)
                    if channel:
                        embed = discord.Embed(
                            title="⚠️ Long Session Alert",
                            description=f"Your gaming session has been running for {format_duration(duration)}.\nConsider taking a break! 🎮💤",
                            color=0xffa500
                        )
                        embed.set_footer(text="This is an automated health reminder")
                        
                        await channel.send(embed=embed)
                        logger.info(f"Sent long session warning for guild {session.guild_id}")
                except Exception as e:
                    logger.error(f"Failed to send session warning: {e}")
                    
    except Exception as e:
        logger.error(f"Error in session warnings task: {e}")

@cleanup_sessions.before_loop
async def before_cleanup():
    await bot.wait_until_ready()

@session_warnings.before_loop
async def before_warnings():
    await bot.wait_until_ready()

async def main():
    """Main function to run the bot."""
    try:
        logger.info("🚀 Starting SM64 Co-op DX Discord Bot...")
        await bot.start(BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Invalid bot token. Please check DISCORD_BOT_TOKEN environment variable.")
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        logger.error(traceback.format_exc())
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"🔥 Critical error: {e}")
        logger.error(traceback.format_exc())
