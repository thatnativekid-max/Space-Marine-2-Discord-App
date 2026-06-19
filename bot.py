import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image
import asyncio
from discord.ext import tasks

db_lock = asyncio.Lock()
event_lock = asyncio.Lock()

TOKEN = os.getenv("TOKEN")

DB_FILE = "/data/database.db" 

intents = discord.Intents.default() 
intents.members = True 
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def get_member_days(member: discord.Member):
    if not member.joined_at:
        return 0
    return (datetime.now(timezone.utc) - member.joined_at).days

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

RANKS = {
    25: "Scout",
    100: "Battle Brother",
    300: "Veteran",
    450: "Bladeguard Veteran",
    650: "Sergeant",
    900: "Veteran-Sergeant",
    1200: "Ancient",
    1500: "Lieutenant"
}

SPECIAL_RANKS = {
    "Helix Adept",
    "Tech Adept",
    "Judiciar",
    "Lexicanum"
}

OPERATION_DIFFICULTY = {
    "Substantial": 1,
    "Ruthless": 2,
    "Lethal": 3,
    "Absolute": 4
}

STRATAGEM_DIFFICULTY = {
    "Normal": 3,
    "Hard": 5
}

VICTORY_CHOICES = [
    app_commands.Choice(name="Yes", value="Yes"),
    app_commands.Choice(name="No", value="No"),
]

OPERATION_DIFFICULTY_CHOICES = [
    app_commands.Choice(name="Substantial", value="Substantial"),
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

def safe_split(value):
    if not value or value in ("[]", "None"):
        return []
    return [x for x in value.split(",") if x]
    
def get_user(uid: int | str):
    uid = str(uid)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT aar_points, gene, completed_challenges
        FROM members
        WHERE user_id = ?
    """, (uid,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "aar_points": 0,
            "gene": 0,
            "completed_challenges": []
        }

    return {
        "aar_points": row[0],
        "gene": row[1],
        "completed_challenges": safe_split(row[2])
    }

def backup_database():
    backup_path = "/data/database_backup.db"

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    backup = sqlite3.connect(backup_path)
    conn.backup(backup)
    backup.close()
    conn.close()

async def add_aar_points(member, amount, gene_bonus=0):
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
            SET aar_points = aar_points + ?, gene = gene + ?
            WHERE user_id = ?
        """, (amount, gene_bonus, uid))

        conn.commit()

        cursor.execute("""
            SELECT aar_points, gene, completed_challenges
            FROM members
            WHERE user_id = ?
        """, (uid,))

        row = cursor.fetchone()
        conn.close()

    return {
        "aar_points": row[0],
        "gene": row[1],
        "completed_challenges": safe_split(row[2])
    }

CHALLENGE_REQUIREMENTS = {
    "Scout": {
        "aar_points": 25
    },

    "Battle Brother": {
        "aar_points": 100,
    },
    
    "Lexicanum": {
        "aar_points": 350,
        "approval": True
},
    "Judiciar": {
        "aar_points": 350,
        "approval": True
    },

    "Tech Adept": {
        "aar_points": 350,
        "approval": True
    },

    "Helix Adept": {
        "aar_points": 350,
        "approval": True
    },
    
    "Veteran": {
        "aar_points": 300,
        "days": 30
    },

    "Bladeguard Veteran": {
        "aar_points": 450,
        "approval": True
    },

    "Sergeant": {
        "aar_points": 650
    },

    "Techmarine": {
        "aar_points": 750,
        "approval": True
    },

    "Librarian": {
        "aar_points": 750,
        "approval": True
    },

    "Apothecary": {
        "aar_points": 750,
        "approval": True
    },

    "veteran-Sergeant": {
        "aar_points": 900,
        "approval": True
    },

    "Ancient": {
        "aar_points": 1200,
        "approval": True
    }
}

CHALLENGES = {
    "Scout": {"auto": True},
    "Battle Brother": {"auto": True},
    "Lexicanum": {"auto": False},
    "Judiciar": {"auto": False},
    "Tech Adept": {"auto": False},
    "Helix Adept": {"auto": False},
    "Veteran": {"auto": True},
    "Bladeguard Veteran": {"auto": False},
    "Techmarine": {"auto": False},
    "Sergeant": {"auto": False}, 
    "Librarian": {"auto": False},
    "Apothecary": {"auto": False},
    "Veteran-Sergeant": {"auto": False},
    "Ancient": {"auto": False},
}
CHALLENGE_CHOICES = [
    app_commands.Choice(name=name, value=name)
    for name in CHALLENGES.keys()
]

def get_rank_with_time(member, total):
    days = get_member_days(member)
    rank = "Aspirant"

    for threshold in sorted(RANKS.keys()):
        potential = RANKS[threshold]

        # skip hidden progression ranks
        if potential in SPECIAL_RANKS:
            continue

        if total >= threshold:
            if potential == "Veteran" and days < 30:
                continue
            rank = potential

    return rank

def get_next_rank(total):
    for threshold in sorted(RANKS.keys()):
        rank = RANKS[threshold]

        if rank in SPECIAL_RANKS:
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

    new_rank = get_rank_with_time(member, user["aar_points"])

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

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    
    conn.close()
    backup_database()

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
        SET aar_points = ?, gene = ?, completed_challenges = ?
        WHERE user_id = ?
    """, (
        user["aar_points"],
        user["gene"],
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

async def process_progress(member, points, gene_bonus):
    user = await add_aar_points(member, points, gene_bonus)

    await update_rank_cached(member=member, user=user)

    save_user(member.id, user)
    return user

@bot.tree.command(name="edit_aar_points", description="Add or subtract aar_points from a member")
async def edit_aar_points(
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
    
    cursor.execute("""
        UPDATE members
        SET aar_points = aar_points + ?
        WHERE user_id = ?
    """, (final_amount, str(member.id)))

    conn.commit()
    conn.close()
    backup_database()

    user = get_user(member.id)

    await update_rank_cached(member, user)

    embed = discord.Embed(
        title="AAR points Edited",
        color=discord.Color.orange()
    )

    embed.add_field(name="Member", value=member.mention, inline=False)
    embed.add_field(name="Mode", value=mode, inline=False)
    embed.add_field(name="Changed By", value=final_amount, inline=False)
    embed.add_field(name="New Total Points", value=user["aar_points"], inline=False)
    embed.add_field(name="Gene Seeds", value=user["gene"], inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="player_card")
async def player_card(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()

    member = member or interaction.user
    user = get_user(member.id)

    aar_points = user["aar_points"]
    gene = user["gene"]
    days = get_member_days(member)
    completed = user.get("completed_challenges", [])

    approval_rank = None

    for r in SPECIAL_RANKS:
        if r in completed:
            approval_rank = r
            break

    rank = approval_rank if approval_rank else get_rank_with_time(member, aar_points)
    
    next_rank, next_req = get_next_rank(aar_points)

    if next_rank:
        progress_bar_text = progress_bar(aar_points, next_req)
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
    f"**AAR Points Earned:** {aar_points}\n"
    f"**Gene-Seeds Collected:** {gene}\n"
    "\n"
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
    total_aar_points = (base + gene_bonus) 

    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = get_user(m.id)
        user = await process_progress(m, total_aar_points, gene_bonus)

        aar_points = user["aar_points"]
        gene = user["gene"]


        lines.append(
            f"{m.mention}\n"
            f"{get_progress_text(aar_points)}"
        )

    embed = discord.Embed(title="++𝕺𝖕𝖊𝖗𝖆𝖙𝖎𝖔𝖓 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.red())
    embed.add_field(name="Mission", value=mission.value, inline=False)
    embed.add_field(name="Difficulty", value=f"{difficulty.value} (+{base} Points)", inline=False)

    gene_text = "Found (+1 Points)" if gene_seed.value == "Found" else "None"
    embed.add_field(name="Gene Seed", value=gene_text, inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
    )

@bot.tree.command(name="stratagem_report")
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
    total_aar_points = (base + gene_bonus) 

    difficulty_text = f"{difficulty.value} (+{base} Points)"

    members = build_members(member1, member2, member3)

    lines = []

    for m in members:
        user = get_user(m.id)
        user = await process_progress(m, total_aar_points, gene_bonus)
        aar_points = user["aar_points"]
        gene = user["gene"]

        lines.append(
            f"{m.mention}\n"
            f"{get_progress_text(aar_points)}"
        )

    embed = discord.Embed(title="++𝕾𝖙𝖗𝖆𝖙𝖆𝖌𝖊𝖒 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.gold())
    embed.add_field(name="Mission", value=mission.value, inline=False)
    embed.add_field(name="Difficulty", value=difficulty_text, inline=False)

    gene_text = "Found (+1 Points)" if gene_seed.value == "Found" else "None"
    embed.add_field(name="Gene Seed", value=gene_text, inline=False)

    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
    )

@bot.tree.command(name="siege_report")
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
    total_aar_points = (waves.value // 5) * 2
    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = await process_progress(m, total_aar_points, gene_bonus)
        total = user["aar_points"]
        
        lines.append(f"{m.mention}\nTotal: {total}\n{get_progress_text(total)}")

    embed = discord.Embed(title="++𝕾𝖎𝖊𝖌𝖊 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.blurple())
    embed.add_field(name="Waves Cleared", value=str(waves.value), inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
    )

@bot.tree.command(name="pvp_report")
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
    
    aar_points = 3 if victory.value == "Yes" else 0
    gene_bonus = 0
    total_aar_points = aar_points
    members = build_members(member1, member2, member3)

    embed = discord.Embed(title="++𝕻𝖛𝖕 𝕽𝖊𝖕𝖔𝖗𝖙++", color=discord.Color.green())
    embed.add_field(name="Mode", value=mode, inline=False)
    embed.add_field(name="Victory", value=victory.value, inline=False)

    for m in members:
        user = await process_progress(m, total_aar_points, gene_bonus)

        total = user["aar_points"]
        
        embed.add_field(
            name=m.display_name,
            value=f"+{aar_points} Points\nTotal: {total}\n{get_progress_text(total)}",
            inline=False
        )

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots,
    )

@bot.tree.command(
    name="challenge_progress",
    description="View challenge progression for a member"
)
async def challenge_progress(interaction: discord.Interaction, member: discord.Member = None):

    member = member or interaction.user

    await interaction.response.defer()

    user = get_user(member.id)
    aar_points = user["aar_points"]
    completed = user.get("completed_challenges", [])
    days = get_member_days(member)

    NAME_WIDTH = 28

    dossier = "```ini\n"
    dossier += f"[CHALLENGE DATASLATE - {member.display_name}]\n\n"

    for challenge_name, req in CHALLENGE_REQUIREMENTS.items():

        if challenge_name in completed:
            status = "COMPLETED"
        else:
            status = "PENDING"

        title = challenge_name[:NAME_WIDTH]
        header = title.ljust(NAME_WIDTH) + status
        dossier += header + "\n"

        if "rites" in req:
            dossier += f" Points {aar_points}/{req['aar_points']}\n"

        if "days" in req:
            dossier += f" Days {days}/{req['days']}\n"

        if req.get("approval"):
            dossier += " Officer Approval Required\n"

        dossier += "\n"

    embed = discord.Embed(
        title="Challenge Progress",
        description=dossier,
        color=discord.Color.dark_gold()
    )

    await interaction.followup.send(embed=embed)


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
    except Exception as e:
        print(f"Sync failed: {e}")


bot.run(TOKEN)
