import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timezone
from threading import Thread
from io import BytesIO
from PIL import Image
import asyncio
import traceback
import time 
from discord.ext import tasks
import shutil

db_lock = asyncio.Lock()
event_lock = asyncio.Lock()

TOKEN = os.getenv("TOKEN")

DB_FILE = "/data/database.db" 

BATTLE_REPORT_CHANNEL_ID = 1500525099655102525
TECHSORCIST_RECORDS_CHANNEL_ID = 1505702243666497688
EVENTS_CHANNEL_ID = 1506016793691426936
GREAT_HALL_CHANNEL_ID = 1393664184771936279

intents = discord.Intents.default() 
intents.members = True 
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def is_double_rites_event():
    now = datetime.now(timezone.utc)
    return (7 <= now.day <= 10) or (20 <= now.day <= 23)
  
def init_db(): 
    
    conn = sqlite3.connect(DB_FILE) 
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            rites INTEGER DEFAULT 0,
            gene INTEGER DEFAULT 0,
            relics TEXT DEFAULT '[]',
            completed_challenges TEXT DEFAULT '[]'
        )
    """)

    conn.commit()
    conn.close()

init_db()

def get_member_days(member: discord.Member):
    if not member.joined_at:
        return 0
    return (datetime.now(timezone.utc) - member.joined_at).days

def battle_reports_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.channel_id != BATTLE_REPORT_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ Battle reports may only be used in the designated Battle Reports channel.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

def events_channel_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.channel_id != EVENTS_CHANNEL_ID:
            await interaction.response.send_message(
                "Event requests may only be used in the Events channel.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

def techsorcist_records_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.channel_id != TECHSORCIST_RECORDS_CHANNEL_ID:
            await interaction.response.send_message(
                "This command may only be used in Techsorcist Records.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

async def make_grid_image(attachments, cols=2):
    try:
        MAX_IMAGE_SIZE = 900 # max width/height per image
        MAX_TOTAL_PIXELS = 8_000_000 # hard safety cap

        images = []

        for att in attachments:
            data = await asyncio.wait_for(att.read(), timeout=5)

            bio = BytesIO(data)

            with Image.open(bio) as img:
                  
                img = img.convert("RGB")

                img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))

                images.append(img.copy())
            bio.close()    
            
        if not images:
            return None

        w, h = images[0].size
        rows = (len(images) + cols - 1) // cols
        
        total_width = cols * w
        total_height = rows * h

        if total_width * total_height > MAX_TOTAL_PIXELS:
            print("Grid too large — resizing further")

            scale = (MAX_TOTAL_PIXELS / (total_width * total_height)) ** 0.5

            new_w = int(w * scale)
            new_h = int(h * scale)

            resized = []
            for img in images:
                img = img.resize((new_w, new_h))
                resized.append(img)

            images = resized
            w, h = new_w, new_h
            total_width = cols * w
            total_height = rows * h

        grid = Image.new("RGB", (total_width, total_height), (20, 20, 20))

        for i, img in enumerate(images):
            x = (i % cols) * w
            y = (i // cols) * h
            grid.paste(img, (x, y))

        buffer = BytesIO()
        grid.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        grid.close()
        for img in images:
            img.close()

        return buffer

    except Exception as e:
        print(f"Image processing error: {e}")
        return None
    
class EventApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Administrator permission required.",
                ephemeral=True
            )

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"Approved by {interaction.user}")

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("✅ Event approved.", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Administrator permission required.",
                ephemeral=True
            )

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"Denied by {interaction.user}")

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("❌ Event denied.", ephemeral=True)

# ==================================================
# RANK SYSTEM
# ==================================================

RANKS = {
    24: "Scout",
    95: "Battle Brother",
    150: "Brother-Initiate",
    420: "Veteran",
    600: "Bladeguard Veteran",
    750: "Sergeant",
    900: "Lector",
    1100: "Lector-Sergeant",
    1350: "Ancient",
    1600: "Lieutenant",
    2000: "Almoner",
    2500: "Almoner-Lieutenant"
}

HIDDEN_PROGRESSION_RANKS = {
    "Helix Adept",
    "Tech Adept",
    "Judiciar",
    "Lexicanum"
}

# ==================================================
# RELIC REWARDS SYSTEM
# ==================================================

RELICS = {
    "Hellslayer": {"gene": 25, "rites": 200},
    "Serpent Staff of Sabazius": {"gene": 40, "rites": 250},
    "Cessation": {"gene": 55, "rites": 300},
    "Liber Exorcismus": {"gene": 75, "rites": 350},
    "Expulsiaris": {"gene": 100, "rites": 500},
    "Silent Cry": {"gene": 130, "rites": 675},
    "Exile Plate": {"gene": 150, "rites": 825},
    "Voidbane": {"gene": 175, "rites": 1000},
    "Daemonarchia Claviculus": {"gene": 200, "rites": 1225},
}

CHALLENGE_TO_RANK = {
    "Welcome to the Exorcists": "Scout",
    "Battle Brother": "Battle Brother",
    "Initiate Trials": "Brother-Initiate",
    "Scholar": "Lexicanum",
    "Emperor's Might": "Judiciar",
    "Mechanicus": "Tech Adept",
    "Thrice Sealed Chalice": "Helix Adept",
    "Veteran Honours": "Veteran",
    "Exorcist Sergeant": "Sergeant",
    "Emperor's Blade": "Bladeguard Veteran",
    "Enochian": "Enochian Guard",
    "Apothecary": "Apothecary",
    "Techmarine": "Techmarine",
    "Banisher": "Librarian",
    "Experienced Orison Member": "Lector",
    "Warden of Purgatomb": "Daemonium Palatinae",
    "Orison Leader": "Lector-Sergeant",
    "Standard Bearer": "Ancient"

}
# ==================================================
# DIFFICULTY VALUES
# ==================================================

OPERATION_DIFFICULTY = {
    "Ruthless": 2,
    "Lethal": 3,
    "Absolute": 4
}

STRATAGEM_DIFFICULTY = {
    "Normal": 3,
    "Hard": 5
}

# ==================================================
# DROPDOWN CHOICES
# ==================================================

VICTORY_CHOICES = [
    app_commands.Choice(name="Yes", value="Yes"),
    app_commands.Choice(name="No", value="No"),
]

OPERATION_DIFFICULTY_CHOICES = [
    app_commands.Choice(name="Ruthless", value="Ruthless"),
    app_commands.Choice(name="Lethal", value="Lethal"),
    app_commands.Choice(name="Absolute", value="Absolute"),
]

STRATAGEM_DIFFICULTY_CHOICES = [
    app_commands.Choice(name="Normal", value="Normal"),
    app_commands.Choice(name="Hard", value="Hard"),
]

WAVE_CHOICES = [
    app_commands.Choice(name="5", value=5),
    app_commands.Choice(name="10", value=10),
    app_commands.Choice(name="15", value=15),
    app_commands.Choice(name="20", value=20),
]

GENE_CHOICES = [
    app_commands.Choice(name="Found", value="Found"),
    app_commands.Choice(name="Not Found", value="Not Found"),
]

MISSION_LIST = [
    "Inferno", "Decapitation", "Vox Liberatis", "Reliquary",
    "Fall of Atreus", "Ballistic Engine", "Termination",
    "Obelisk", "Exfiltration", "Vortex",
    "Reclamation", "Disruption", "Purgation"
]

MISSION_CHOICES = [app_commands.Choice(name=m, value=m) for m in MISSION_LIST]

# ==================================================
# DATA SYSTEM
# ==================================================
def safe_split(value):
    if not value or value in ("[]", "None"):
        return []
    return [x for x in value.split(",") if x]
    
def get_user(uid: int | str):
    uid = str(uid)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT rites, gene, relics, completed_challenges
        FROM members
        WHERE user_id = ?
    """, (uid,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "rites": 0,
            "gene": 0,
            "relics": [],
            "completed_challenges": []
        }

    return {
        "rites": row[0],
        "gene": row[1],
        "relics": safe_split(row[2]),
        "completed_challenges": safe_split(row[3])
    }

def backup_database():
    backup_path = "/data/database_backup.db"

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    backup = sqlite3.connect(backup_path)
    conn.backup(backup)
    backup.close()
    conn.close()

async def add_rites(member, amount, gene_bonus=0):
    if is_double_rites_event():
        amount *=2

    uid = str(member.id)

    async with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO members (user_id)
            VALUES (?)
        """, (uid,))

        cursor.execute("""
            UPDATE members
            SET rites = rites + ?, gene = gene + ?
            WHERE user_id = ?
        """, (amount, gene_bonus, uid))

        conn.commit()

        cursor.execute("""
            SELECT rites, gene, relics, completed_challenges
            FROM members
            WHERE user_id = ?
        """, (uid,))

        row = cursor.fetchone()
        conn.close()

    return {
        "rites": row[0],
        "gene": row[1],
        "relics": row[2].split(",") if row[2] else [],
        "completed_challenges": row[3].split(",") if row[3] else []
    }


# ==================================================
# CHALLENGE SYSTEM
# ==================================================
CHALLENGE_REQUIREMENTS = {
    "Scout": {
        "rites": 24
    },

    "Battle Brother": {
        "rites": 95,
        "days": 7
    },

    "Brother-Initiate": {
        "rites": 150,
        "approval": True
    },
    "Lexicanum": {
        "rites": 350,
        "approval": True
},
    "Judiciar": {
        "rites": 300,
        "approval": True
    },

    "Tech Adept": {
        "rites": 250,
        "approval": True
    },

    "Helix Adept": {
        "rites": 200,
        "approval": True
    },
    
    "Veteran": {
        "rites": 420,
        "days": 30
    },

    "Bladeguard Veteran": {
        "rites": 600,
        "approval": True
    },

    "Enochian Guard": {
        "rites": 420,
        "approval": True,
        "special": "Must be Veteran"
    },

    "Sergeant": {
        "rites": 750
    },

    "Techmarine": {
        "rites": 750,
        "approval": True
    },

    "Librarian": {
        "rites": 750,
        "approval": True
    },

    "Apothecary": {
        "rites": 750,
        "approval": True
    },

    "Lector": {
        "rites": 900,
        "approval": True
    },

    "Daemonium Palatinae": {
        "approval": True,
        "days": 60,
        "special": "Must be Enochian Guard"
    },

    "Lector-Sergeant": {
        "rites": 1100,
        "approval": True
    },

    "Ancient": {
        "rites": 1350,
        "approval": True
    }
}

CHALLENGES = {
    "Scout": {"emoji": "<:11_12th_co:1499186125611208764> ", "auto": True},
    "Battle Brother": {"emoji": "<:10th_co:1499184291878277180> ", "auto": True},
    "Brother-Initiate": {"emoji": "<:Brother_Initiate:1506609321264414893> ", "auto": False},
    "Lexicanum": {"emoji": "📖", "auto": False},
    "Judiciar": {"emoji": "<:judiciar:1506715094455947305>", "auto": False},
    "Tech Adept": {"emoji": "⚙️", "auto": False},
    "Helix Adept": {"emoji": "⛑️", "auto": False},
    "Veteran": {"emoji": "<:veteran:1506715250081398914> ","auto": True},
    "Bladeguard Veteran": {"emoji": "<:1st_co:1499188889766854746> ", "auto": False},
    "Enochian Guard": {"emoji": "<:enochian_guard:1499476859275055246> ", "auto": False},
    "Techmarine": {"emoji": "<:techmarine:1499184650097131571> ", "auto": False},
    "Sergeant": {"emoji": "<:Sergeant:1506742675406192730>", "auto": False}, 
    "Librarian": {"emoji": "<:librarianj:1499184409322979500> ", "auto": False},
    "Apothecary": {"emoji": "<:apothecary:1499184375093268611> ", "auto": False},
    "Lector": {"emoji": "<:lector:1506715579715817693>", "auto": False},
    "Daemonium Palatinae": {"emoji": "<:daemonium_palatinae:1506715777384841306> ", "auto": False},
    "Lector-Sergeant": {"emoji": "<:lector_sergeant:1506715658170142923>", "auto": False},
    "Ancient": {"emoji": "<:ancient:1506717087656317079>", "auto": False},
}
CHALLENGE_CHOICES = [
    app_commands.Choice(name=name, value=name)
    for name in CHALLENGES.keys()
]
# ==================================================
# RANK LOGIC
# ==================================================

def get_rank_with_time(member, total):
    days = get_member_days(member)
    rank = "Aspirant"

    for threshold in sorted(RANKS.keys()):
        potential = RANKS[threshold]

        # skip hidden progression ranks
        if potential in HIDDEN_PROGRESSION_RANKS:
            continue

        if total >= threshold:
            if potential == "Veteran" and days < 30:
                continue
            rank = potential

    return rank

def get_next_rank(total):
    for threshold in sorted(RANKS.keys()):
        rank = RANKS[threshold]

        if rank in HIDDEN_PROGRESSION_RANKS:
            continue

        if total < threshold:
            return rank, threshold

    return None, None

def progress_bar(current, target, length=18):
    if not target:
        return "████████████████ MAX"
    filled = int((current / target) * length)
    return "█" * filled + "░" * (length - filled) + f" {current}/{target}"

def get_progress_text(total):
    next_rank, next_req = get_next_rank(total)
    if not next_rank:
        return "MAX RANK"
    return f"Next: {next_rank}\n{progress_bar(total, next_req)}"

async def assign_rank_role(member: discord.Member, role_name: str):
    if not role_name:
        return

    role = discord.utils.get(member.guild.roles, name=role_name)
    if not role:
        return

    rank_roles = [r for r in member.guild.roles if r.name in RANKS.values()]
    await member.remove_roles(*rank_roles, reason="Rank sync")

    await member.add_roles(role, reason="Challenge approval rank grant")

async def update_rank_cached(member: discord.Member, user: dict):
    uid = str(member.id)

    new_rank = get_rank_with_time(member, user["rites"])

    roles = {role.name: role for role in member.guild.roles}

    rank_roles = [roles.get(r) for r in RANKS.values()]
    rank_roles = [r for r in rank_roles if r]

    remove = [r for r in rank_roles if r in member.roles and r.name != new_rank]

    if remove:
        await member.remove_roles(*remove)

    new_role = roles.get(new_rank)
    if new_role:
        await member.add_roles(new_role)

    if new_rank in CHALLENGES:
        if new_rank not in user["completed_challenges"]:
            user["completed_challenges"].append(new_rank)

    save_user(member.id, user)
    # SINGLE DB WRITE ONLY
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()

    conn.commit()
    conn.close()
    backup_database()
    
async def check_relics_cached(member: discord.Member, user: dict):
    uid = str(member.id)

    unlocked = []

    for relic, req in RELICS.items():
        if relic in user["relics"]:
            continue

        if user.get("gene", 0) >= req["gene"] and user.get("rites", 0) >= req["rites"]:
            user["relics"].append(relic)
            unlocked.append(relic)

    if unlocked:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()

        conn.commit()
        conn.close()
        save_user(member.id, user)
        backup_database()
        
    return unlocked

def safe_join(value):
    if not value:
        return ""
    return ",".join(value)

def save_user(user_id, user):
    user["completed_challenges"] = list(set(user["completed_challenges"]))
    
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE members
        SET rites = ?, gene = ?, relics = ?, completed_challenges = ?
        WHERE user_id = ?
    """, (
        user["rites"],
        user["gene"],
        safe_join(user["relics"]),
        safe_join(user["completed_challenges"]),
        str(user_id)
    ))
    
    conn.commit()
    conn.close()
    backup_database()

async def safe_defer(interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()
        
def build_members(*members):
    return [m for m in members if m]


async def send_gallery(interaction, embed, screenshots, content=None):
    if not screenshots:
        await interaction.followup.send(content=content, embed=embed)
        return

    grid_image = await make_grid_image(screenshots, 2)

    if not grid_image:
        await interaction.followup.send(content=content, embed=embed)
        return

    file = discord.File(grid_image, filename="grid.png")
    embed.set_image(url="attachment://grid.png")

    await interaction.followup.send(
        content=content,
        embed=embed,
        file=file
    )

    grid_image.close()

async def process_progress(member, rites, gene_bonus):
    user = await add_rites(member, rites, gene_bonus)

    new_relics = await check_relics_cached(member=member, user=user)
    await update_rank_cached(member=member, user=user)

    user["new_relics"] = new_relics

    save_user(member.id, user)
    
    return user

async def announce_relics(interaction, member, user):
    for r in user.get("new_relics", []):
        await interaction.channel.send(
            f"{member.mention} has unlocked relic: {r} "
        )

def announce_double_rites(bot):
    channel = bot.get_channel(GREAT_HALL_CHANNEL_ID)
    if not channel:
        return

    if is_double_rites_event():
        # prevent spam on reconnects
        if getattr(bot, "_double_rites_announced", False):
            return

        bot._double_rites_announced = True

        return channel.send(
            "**+++ 𝔇𝔬𝔲𝔟𝔩𝔢 XP 𝔄𝔠𝔱𝔦𝔳𝔢 +++**\n\n"
            "Report to your battle stations armed and ready!\n"
            "Now is the time to commit great deeds in the name of the Emperor!\n\n"
            "Event takes place between 7th-10th and 20th-23rd each month!"
        )
        
def get_next_relic(user):
    rites = user.get("rites", 0)
    gene = user.get("gene", 0)

    for relic, req in sorted(RELICS.items(), key=lambda x: x[1]["rites"]):
        if relic in user.get("relics", []):
            continue

        remaining = req["rites"] - rites
        if remaining < 0:
            remaining = 0

        return relic, req["rites"], remaining

    return None, None, None

@bot.tree.command(name="edit_rites", description="Add or subtract rites from a member")
async def edit_rites(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int,
    mode: str,  # "add" or "subtract"
    reason: str = "None"
):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)

    await safe_defer(interaction)

    if mode not in ["add", "subtract"]:
        return await interaction.followup.send("Mode must be `add` or `subtract`.")

    if amount <= 0:
        return await interaction.followup.send("Amount must be greater than 0.")

    final_amount = amount if mode == "add" else -amount

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO members (user_id)
        VALUES (?)
    """, (str(member.id),))

    # Apply change
    cursor.execute("""
        UPDATE members
        SET rites = rites + ?
        WHERE user_id = ?
    """, (final_amount, str(member.id)))

    conn.commit()
    conn.close()
    backup_database()

    user = get_user(member.id)

    await update_rank_cached(member, user)

    embed = discord.Embed(
        title="Rites Edited",
        color=discord.Color.orange()
    )

    embed.add_field(name="Member", value=member.mention, inline=False)
    embed.add_field(name="Mode", value=mode, inline=False)
    embed.add_field(name="Changed By", value=final_amount, inline=False)
    embed.add_field(name="New Total Rites", value=user["rites"], inline=False)
    embed.add_field(name="Gene Seeds", value=user["gene"], inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="player_card")
async def player_card(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()

    member = member or interaction.user
    user = get_user(member.id)

    rites = user["rites"]
    gene = user["gene"]
    days = get_member_days(member)
    completed = user.get("completed_challenges", [])

    approval_rank = None

    for r in HIDDEN_PROGRESSION_RANKS:
        if r in completed:
            approval_rank = r
            break

    rank = approval_rank if approval_rank else get_rank_with_time(member, rites)
    
    badges = "".join(
        f"{CHALLENGES[name]['emoji']} "
        for name in CHALLENGES
        if name in completed
    ).strip()

    relics = user.get("relics", [])
    relic_text = "\n".join(f"• {r}" for r in relics) if relics else "None recorded"
    relic_section = f"Relics:\n{relic_text}"

    next_rank, next_req = get_next_rank(rites)

    if next_rank:
        progress_bar_text = progress_bar(rites, next_req)
        progress_section = (
            f"Next Rank: **{next_rank}**\n"
            f"{progress_bar_text}"
        )
    else:
        progress_section = f"\nMAX RANK ACHIEVED"

    dossier = (
    f"☠ **++SERVICE RECORD++** ☠\n"
    f"◆━━━━━━━━━━━━━━━━━━━━━━━━━━━◆\n"
    f"**Designation:** {member.display_name}\n"
    f"**Rank:** ✠ *{rank.upper()}* ✠\n"
    f"**Years in Service:** {days} years\n"
    "\n"
    f"⚔ **++COMBAT LOG++** ⚔\n"
    f"◆━━━━━━━━━━━━━━━━━━━━━━━━━━━◆\n"
    f"**Service Rites Earned:** {rites}\n"
    f"**Gene-Seeds Collected:** {gene}\n"
    "\n"
    f"✠ **++MARKS OF VALOR++** ✠\n"
    f"◆━━━━━━━━━━━━━━━━━━━━━━━━━━━◆\n"
    f"{badges if badges else '*No honors recorded in the Librarium*'}\n"
    "\n"
    f"🕯 **++SANCTIFIED RELICS++** 🕯\n"
    f"◆━━━━━━━━━━━━━━━━━━━━━━━━━━━◆\n"
    f"{relic_text if relics else '*None entrusted by the Chapter*'}\n"
)

    embed = discord.Embed(
    title="☠️ ...ADEPTUS ASTARTES... ☠️\u200b\n//DATASLATE//",
    description=dossier,
    color=discord.Color.dark_red()
)


    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="...ASCENSION THRESHOLD...",
        value=progress_section,
        inline=False
    )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="operation_report")
@battle_reports_only()
@app_commands.choices(
    mission=MISSION_CHOICES,
    difficulty=OPERATION_DIFFICULTY_CHOICES,
    gene_seed=GENE_CHOICES
)
async def operation_report(
    interaction: discord.Interaction,
    mission: app_commands.Choice[str],
    difficulty: app_commands.Choice[str],
    gene_seed: app_commands.Choice[str],
    member1: discord.Member,
    screenshot1: discord.Attachment,
    screenshot2: discord.Attachment,
    member2: discord.Member = None,
    member3: discord.Member = None,
    screenshot3: discord.Attachment = None,
    screenshot4: discord.Attachment = None
):

    await safe_defer(interaction)
    
    base = OPERATION_DIFFICULTY[difficulty.value]
    gene_bonus = 1 if gene_seed.value == "Found" else 0
    total_rites = (base + gene_bonus) 

    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = get_user(m.id)
        next_relic, relic_req, relic_remaining = get_next_relic(user)
        user = await process_progress(m, total_rites, gene_bonus)

        rites = user["rites"]
        gene = user["gene"]

        await announce_relics(interaction, m, user)

        if next_relic:
            relic_data = RELICS[next_relic]

            relic_text = (
                f"Next Relic: {next_relic}\n"
                f"Gene Seed: {gene}/{relic_data['gene']}\n\n"
            )
        else:
            relic_text = (
                "All Relics Unlocked\n\n"
            )

        lines.append(
            f"{m.mention}\n"
            f"{relic_text}"
            f"{get_progress_text(rites)}"
        )

    embed = discord.Embed(title="++𝕺𝖕𝖊𝖗𝖆𝖙𝖎𝖔𝖓 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.red())
    embed.add_field(name="Mission", value=mission.value, inline=False)
    embed.add_field(name="Difficulty", value=f"{difficulty.value} (+{base} Rites)", inline=False)

    gene_text = "Found (+1 Rites)" if gene_seed.value == "Found" else "None"
    embed.add_field(name="Gene Seed", value=gene_text, inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
        "The daemons are banished! Your willpower remains strong as steel. "
        "Let us ensure your tools are equally resolute."
    )

@bot.tree.command(name="stratagem_report")
@battle_reports_only()
@app_commands.choices(
    mission=MISSION_CHOICES,
    difficulty=STRATAGEM_DIFFICULTY_CHOICES,
    gene_seed=GENE_CHOICES
)
async def stratagem_report(
    interaction: discord.Interaction,
    mission: app_commands.Choice[str],
    difficulty: app_commands.Choice[str],
    gene_seed: app_commands.Choice[str],
    member1: discord.Member,
    screenshot1: discord.Attachment,
    screenshot2: discord.Attachment,
    member2: discord.Member = None,
    member3: discord.Member = None,
    screenshot3: discord.Attachment = None,
    screenshot4: discord.Attachment = None
):

    await safe_defer(interaction)

    base = STRATAGEM_DIFFICULTY[difficulty.value]
    gene_bonus = 1 if gene_seed.value == "Found" else 0
    total_rites = (base + gene_bonus) 

    difficulty_text = f"{difficulty.value} (+{base} Rites)"

    members = build_members(member1, member2, member3)

    lines = []

    for m in members:
        user = get_user(m.id)
        next_relic, relic_req, relic_remaining = get_next_relic(user)
        user = await process_progress(m, total_rites, gene_bonus)
        rites = user["rites"]
        gene = user["gene"]

        await announce_relics(interaction, m, user)

        next_relic, relic_req, relic_remaining = get_next_relic(user)

        if next_relic:
            relic_data = RELICS[next_relic]
            relic_text = (
                f"Next Relic: {next_relic}\n"
                f"Gene Seeds: {gene}/{relic_data['gene']}\n\n"
            )
        else:
            relic_text = "All Relics Unlocked\n\n"

        lines.append(
            f"{m.mention}\n"
            f"{relic_text}"
            f"{get_progress_text(rites)}"
        )

    embed = discord.Embed(title="++𝕾𝖙𝖗𝖆𝖙𝖆𝖌𝖊𝖒 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.gold())
    embed.add_field(name="Mission", value=mission.value, inline=False)
    embed.add_field(name="Difficulty", value=difficulty_text, inline=False)

    gene_text = "Found (+1 Rites)" if gene_seed.value == "Found" else "None"
    embed.add_field(name="Gene Seed", value=gene_text, inline=False)

    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
        "...binaric whirring..."
        "[EXORCISM] protocols completed. The warp-taint is removed. "
        "Your wargear is sanctified."
    )

@bot.tree.command(name="siege_report")
@battle_reports_only()
@app_commands.choices(waves=WAVE_CHOICES)
async def siege_report(interaction: discord.Interaction,
    waves: app_commands.Choice[int],
    member1: discord.Member,
    screenshot1: discord.Attachment,
    screenshot2: discord.Attachment,
    member2: discord.Member = None,
    member3: discord.Member = None,
    screenshot3: discord.Attachment = None,
    screenshot4: discord.Attachment = None
):
    await safe_defer(interaction)
    
    gene_bonus = 0
    total_rites = (waves.value // 5) * 2
    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = await process_progress(m, total_rites, gene_bonus)
        total = user["rites"]

        await announce_relics(interaction, m, user)
        
        lines.append(f"{m.mention}\nTotal: {total}\n{get_progress_text(total)}")

    embed = discord.Embed(title="++𝕾𝖎𝖊𝖌𝖊 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.blurple())
    embed.add_field(name="Waves Cleared", value=str(waves.value), inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
        "Mission efficiency: (97%). "
        "Daemonic presence: (0%). "
        "A satisfactory outcome, my Lord. "
        "Your flesh has proved to be a durable vessel."
    )

@bot.tree.command(name="pvp_report")
@battle_reports_only()
@app_commands.choices(victory=VICTORY_CHOICES)
@app_commands.describe(
    mode="PvP mode (e.g. Annihilation, Sieze Ground, C&C)"
)
async def pvp_report(
    interaction: discord.Interaction,
    mode: str,
    victory: app_commands.Choice[str],
    member1: discord.Member,
    screenshot1: discord.Attachment,
    screenshot2: discord.Attachment,
    member2: discord.Member = None,
    member3: discord.Member = None,
    screenshot3: discord.Attachment = None,
    screenshot4: discord.Attachment = None
):
    await safe_defer(interaction)
    
    rites = 3 if victory.value == "Yes" else 0
    gene_bonus = 0
    total_rites = rites
    members = build_members(member1, member2, member3)

    embed = discord.Embed(title="++𝕻𝖛𝖕 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.green())
    embed.add_field(name="Mode", value=mode, inline=False)
    embed.add_field(name="Victory", value=victory.value, inline=False)

    for m in members:
        user = await process_progress(m, total_rites, gene_bonus)

        total = user["rites"]

        await announce_relics(interaction, m, user)
        
        embed.add_field(
            name=m.display_name,
            value=f"+{rites} Rites\nTotal: {total}\n{get_progress_text(total)}",
            inline=False
        )

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
        "... [Combat efficiency confirmed. Daemonium containment holding [IN PROGRESS]. Data-transfer complete.]"
    )

@bot.event
async def on_ready():
    global db_lock, event_lock

    if db_lock is None:
        db_lock = asyncio.Lock()

    if event_lock is None:
        event_lock = asyncio.Lock()

    print(f"Logged in as {bot.user}")

    try:
        if getattr(bot, "synced", False):
            return

        await bot.tree.sync()
        bot.synced = True
        print("Slash commands synced.")
        await announce_double_rites(bot)
    except Exception as e:
        print(f"Sync failed: {e}")


bot.run(TOKEN)
