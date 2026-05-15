import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from flask import Flask
from threading import Thread

# ==============================
# KEEP ALIVE SERVER
# ==============================

app = Flask("")

@app.route("/")
def home():
    return "Bot is alive"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
    
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# ==================================================
# RANK SYSTEM
# ==================================================

RANKS = {
    24: "Scout",
    75: "Battle Brother",
    125: "Brother-Initiate",
    250: "Veteran",
    350: "Bladeguard Veteran",
    500: "Sergeant",
    650: "Lector",
    725: "Lector-Sergeant",
    850: "Ancient",
    1200: "Lieutenant",
    1500: "Almoner",
    2000: "Almoner-Lieutenant"
}

# ==================================================
# RELIC REWARDS SYSTEM
# ==================================================

RELICS = {
    "Hellslayer": {"gene": 45, "rites": 125},
    "Serpent Staff of Sabazius": {"gene": 65, "rites": 125},
    "Cessation": {"gene": 75, "rites": 250},
    "Liber Exorcismus": {"gene": 85, "rites": 250},
    "Expulsiaris": {"gene": 90, "rites": 350},
    "Silent Cry": {"gene": 100, "rites": 500},
    "Exile Plate": {"gene": 120, "rites": 650},
    "Voidbane": {"gene": 135, "rites": 650},
    "Daemonarchia Claviculus": {"gene": 200, "rites": 1200},
}

CHALLENGE_TO_RANK = {
    "Welcome to the Exorcists": "Scout",
    "Battle Brother": "Battle Brother",
    "Initiate Trials": "Brother-Initiate",
    "Scholar": "Lexicanum",
    "Emperor's Might": "Judiciar",
    "Mechanicus": "Tech Adept",
    "Thrice Sealed Chalice": "Helix Adept",
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
    "Reclamation", "Disruption"
]

MISSION_CHOICES = [app_commands.Choice(name=m, value=m) for m in MISSION_LIST]

# ==================================================
# DATA SYSTEM
# ==================================================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"members": {}}

    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"members": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def ensure_user(user: dict):
    """Guarantees all required fields exist for a user."""
    user.setdefault("rites", 0)
    user.setdefault("gene", 0)
    user.setdefault("relics", [])
    user.setdefault("completed_challenges", [])
    return user

def add_rites(member: discord.Member, amount: int, gene: int = 0):
    data = load_data()
    uid = str(member.id)

    # Create user if missing
    if uid not in data["members"]:
        data["members"][uid] = {}

    # Load + normalize user
    user = ensure_user(data["members"][uid])

    # Update values
    user["rites"] += amount
    user["gene"] += gene

    # Save back into main data structure
    data["members"][uid] = user
    save_data(data)

    return user

# ==================================================
# CHALLENGE SYSTEM
# ==================================================
CHALLENGE_REQUIREMENTS = {
    "Scout": {
        "rites": 24
    },

    "Battle Brother": {
        "rites": 75,
        "days": 7
    },

    "Brother-Initiate": {
        "rites": 125,
        "approval": True
    },
    "Lexicanum": {
        "rites": 125,
        "approval": True
},
    "Judiciar": {
        "rites": 125,
        "approval": True
    },

    "Tech Adept": {
        "rites": 125,
        "approval": True
    },

    "Helix Adept": {
        "rites": 125,
        "approval": True
    },

    "Veteran": {
        "rites": 250,
        "days": 30
    },

    "Bladeguard Veteran": {
        "rites": 350,
        "approval": True
    },

    "Enochian Guard": {
        "rites": 0,
        "approval": True,
        "special": "Must be Veteran"
    },

    "Sergeant": {
        "rites": 500
    },

    "Techmarine": {
        "rites": 500,
        "approval": True
    },

    "Librarian": {
        "rites": 500,
        "approval": True
    },

    "Apothecary": {
        "rites": 500,
        "approval": True
    },

    "Lector": {
        "rites": 650,
        "approval": True
    },

    "Daemonium Palatinae": {
        "approval": True,
        "days": 60,
        "special": "Must be Enochian Guard"
    },

    "Lector-Sergeant": {
        "rites": 725,
        "approval": True
    },

    "Ancient": {
        "rites": 850,
        "approval": True
    }
}

CHALLENGES = {
    "Scout": {"emoji": "🔥", "auto": True},
    "Battle Brother": {"emoji": "🪖", "auto": True},
    "Brother-Initiate": {"emoji": "🕯️", "auto": False},
    "Lexicanum": {"emoji": "📚", "auto": False},
    "Judiciar": {"emoji": "💀", "auto": False},
    "Tech Adept": {"emoji": "🤖", "auto": False},
    "Helix Adept": {"emoji": "⛑️", "auto": False},
    "Bladeguard Veteran": {"emoji": "⚔️", "auto": False},
    "Enochian Guard": {"emoji": "⛓️", "auto": False},
    "Techmarine": {"emoji": "⚙️", "auto": False},
    "Librarian": {"emoji": "📖", "auto": False},
    "Apothecary": {"emoji": "⚕️", "auto": False},
    "Lector": {"emoji": "🧿", "auto": False},
    "Daemonium Palatinae": {"emoji": "🪦", "auto": False},
    "Lector-Sergeant": {"emoji": "☠️", "auto": False},
    "Ancient": {"emoji": "📜", "auto": False},
}
CHALLENGE_CHOICES = [
    app_commands.Choice(name=name, value=name)
    for name in CHALLENGES.keys()
]
# ==================================================
# RANK LOGIC
# ==================================================

def get_rank_with_time(member: discord.Member, total):

    days = (datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0

    rank = "Initiate"

    for threshold in sorted(RANKS.keys()):
        if total >= threshold:
            potential = RANKS[threshold]

            # Veteran requires 30 days
            if potential == "Veteran" and days < 30:
                continue

            rank = potential

    return rank

def get_next_rank(total):
    for threshold in sorted(RANKS.keys()):
        if total < threshold:
            return RANKS[threshold], threshold
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

async def update_rank(member: discord.Member, total: int):
    data = load_data()
    uid = str(member.id)

    if uid not in data["members"]:
        return

    user = data["members"][uid]
    user.setdefault("completed_challenges", [])

    new_rank = get_rank_with_time(member, total)

    roles = {role.name: role for role in member.guild.roles}

    # Remove old rank roles
    for r in RANKS.values():
        role = roles.get(r)
        if role and role in member.roles:
            await member.remove_roles(role)

    # Add new rank role
    new_role = roles.get(new_rank)
    if new_role:
        await member.add_roles(new_role)

    # Auto-complete challenge if applicable
    if new_rank in CHALLENGES:
        challenge = CHALLENGES[new_rank]
        if challenge["auto"] and new_rank not in user["completed_challenges"]:
            user["completed_challenges"].append(new_rank)

    save_data(data)

async def check_relics(member: discord.Member):
    data = load_data()
    uid = str(member.id)

    if uid not in data["members"]:
        return []

    user = data["members"][uid]

    # 🔧 Auto-fix missing keys (backwards compatibility)
    if "relics" not in user:
        user["relics"] = []
    if "gene" not in user:
        user["gene"] = 0
    if "rites" not in user:
        user["rites"] = 0

    unlocked = []

    for relic, req in RELICS.items():
        if relic in user["relics"]:
            continue

        if user["gene"] >= req["gene"] and user["rites"] >= req["rites"]:
            user["relics"].append(relic)
            unlocked.append(relic)

    if unlocked:
        save_data(data)

    return unlocked

# ==================================================
# HELPERS
# ==================================================

def build_members(m1, m2=None, m3=None):
    return [m for m in [m1, m2, m3] if m]

async def send_gallery(interaction, embed, screenshots):
    embeds = [embed]

    for shot in screenshots:
        img_embed = discord.Embed()
        img_embed.set_image(url=shot.url) # 🔥 FIX
        embeds.append(img_embed)

    await interaction.followup.send(embeds=embeds)

# ==================================================
# ADMIN COMMAND
# ==================================================

@bot.tree.command(name="add_rites")
async def add_rites_cmd(interaction: discord.Interaction, member: discord.Member, amount: int, reason: str = "None"):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ No permission.",
            ephemeral=True
        )

    await interaction.response.defer()

    user = ensure_user(add_rites(member, amount))

    rites = user["rites"]
    gene = user["gene"]

    await update_rank(member, rites)

    embed = discord.Embed(title="🛠️ Admin Update", color=discord.Color.orange())
    embed.add_field(name="Member", value=member.mention, inline=False)
    embed.add_field(name="Added", value=amount, inline=False)
    embed.add_field(name="Total Rites", value=rites, inline=False)
    embed.add_field(name="Gene Seeds", value=gene, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="approve_challenge", description="Officer approval for challenge completion")
@app_commands.choices(challenge=CHALLENGE_CHOICES)
async def approve_challenge(
    interaction: discord.Interaction,
    member: discord.Member,
    challenge: app_commands.Choice[str]
):
    # Officer permission check
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message(
            "❌ You do not have permission.",
            ephemeral=True
        )

    await interaction.response.defer()

    data = load_data()
    uid = str(member.id)

    if uid not in data["members"]:
        return await interaction.followup.send("Member has no data.")

    user = ensure_user(data["members"][uid])

    challenge_name = challenge.value

    if challenge_name in user["completed_challenges"]:
        return await interaction.followup.send("Already completed.")

    # Mark challenge complete
    user["completed_challenges"].append(challenge_name)

    # 🔥 STEP 3 HAPPENS HERE 🔥
    role_name = CHALLENGE_TO_RANK.get(challenge_name)
    if role_name:
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role:
            await member.add_roles(role)

    save_data(data)

    await interaction.followup.send(
        f"✅ {member.mention} has completed **{challenge_name}** and been promoted."
    )
# ==================================================
# PLAYER CARD
# ==================================================

@bot.tree.command(name="player_card")
async def player_card(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()  # 🔥 FIX
    member = member or interaction.user
    data = load_data()
    user = ensure_user(data["members"].get(str(member.id), {}))

    rites = user["rites"]
    gene = user["gene"]

    days = (datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0

    embed = discord.Embed(title="🪪 Service Record", color=discord.Color.purple())
    embed.set_thumbnail(url=member.display_avatar.url)

    rank = get_rank_with_time(member, rites)
    completed = user.get("completed_challenges", [])

    emoji_display = ""
    for rank_name in CHALLENGES.keys():
        if rank_name in completed:
            emoji_display += CHALLENGES[rank_name]["emoji"] + " "

    embed.add_field(name="Rank", value=f"{rank} {emoji_display}", inline=False)
    embed.add_field(name="Total Rites", value=rites, inline=False)
    embed.add_field(name="Gene Seeds Found", value=gene, inline=False)
    embed.add_field(name="Time in Chapter", value=f"{days} days", inline=False)

    relic_list = user.get("relics", [])
    relic_display = "\n".join(relic_list) if relic_list else "None"

    embed.add_field(name="Relics Earned", value=relic_display, inline=False)
    embed.add_field(name="Progress", value=get_progress_text(rites), inline=False)

    await interaction.followup.send(embed=embed)

# ==================================================
# OPERATION REPORT
# ==================================================

@bot.tree.command(name="operation_report")
@app_commands.choices(
    mission=MISSION_CHOICES,
    difficulty=OPERATION_DIFFICULTY_CHOICES,
    gene_seed=GENE_CHOICES
)
async def operation_report(interaction: discord.Interaction,
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

    await interaction.response.defer() # 🔥 FIX

    base = OPERATION_DIFFICULTY[difficulty.value]
    gene_bonus = 1 if gene_seed.value == "Found" else 0
    total_rites = base + gene_bonus

    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = add_rites(m, total_rites, gene_bonus)

        rites = user["rites"]
        gene = user["gene"]

        await update_rank(m, rites)
        new_relics = await check_relics(m)

        if new_relics:
            await interaction.channel.send(
                f"🏆 {m.mention} has unlocked relic(s):\n" +
                "\n".join([f"⚜ {r}" for r in new_relics])
            )
        lines.append(f"{m.mention}\nTotal: {rites}\n{get_progress_text(rites)}")

    embed = discord.Embed(title="⚔️ Operation Report", color=discord.Color.red())
    embed.add_field(name="Mission", value=mission.value, inline=False)
    embed.add_field(name="Difficulty", value=difficulty.value, inline=False)
    embed.add_field(name="Gene Seed", value=gene_seed.value, inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots)

    await interaction.followup.send(
        "The daemons are banished! Your willpower remains strong as steel. "
        "Let us ensure your tools are equally resolute."
    )

# ==================================================
# STRATAGEM REPORT
# ==================================================

@bot.tree.command(name="stratagem_report")
@app_commands.choices(
    mission=MISSION_CHOICES,
    difficulty=STRATAGEM_DIFFICULTY_CHOICES,
    gene_seed=GENE_CHOICES
)
async def stratagem_report(interaction: discord.Interaction,
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
    await interaction.response.defer()  # 🔥 FIX

    base = STRATAGEM_DIFFICULTY[difficulty.value]
    gene_bonus = 1 if gene_seed.value == "Found" else 0
    total_rites = base + gene_bonus

    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = add_rites(m, total_rites, gene_bonus)

        rites = user["rites"]
        gene = user["gene"]

        await update_rank(m, rites)
        new_relics = await check_relics(m)

        if new_relics:
            await interaction.channel.send(
                f"🏆 {m.mention} has unlocked relic(s):\n" +
                "\n".join([f"⚜ {r}" for r in new_relics])
            )
        lines.append(f"{m.mention}\nTotal: {rites}\n{get_progress_text(rites)}")

    embed = discord.Embed(title="🧠 Stratagem Report", color=discord.Color.gold())
    embed.add_field(name="Mission", value=mission.value, inline=False)
    embed.add_field(name="Difficulty", value=difficulty.value, inline=False)
    embed.add_field(name="Gene Seed", value=gene_seed.value, inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots)

    await interaction.followup.send(
        "...binaric whirring..."
        "[EXORCISM] protocols completed. The warp-taint is removed. "
        "Your wargear is sanctified."
    )

# ==================================================
# SIEGE REPORT
# ==================================================

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
    await interaction.response.defer()  # 🔥 FIX

    rites = (waves.value // 5) * 2
    members = build_members(member1, member2, member3)
    lines = []

    for m in members:
        user = add_rites(m, rites)

        total = user["rites"]
        gene = user["gene"]

        await update_rank(m, total)
        new_relics = await check_relics(m)

        if new_relics:
            await interaction.channel.send(
                f"🏆 {m.mention} has unlocked relic(s):\n" +
                "\n".join([f"⚜ {r}" for r in new_relics])
            )
        lines.append(f"{m.mention}\nTotal: {total}\n{get_progress_text(total)}")

    embed = discord.Embed(title="🏰 Siege Report", color=discord.Color.blurple())
    embed.add_field(name="Waves Cleared", value=str(waves.value), inline=False)
    embed.add_field(name="Members", value="\n\n".join(lines), inline=False)

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots)

    await interaction.followup.send(
        "Mission efficiency: (97%). "
        "Daemonic presence: (0%). "
        "A satisfactory outcome, my Lord. "
        "Your flesh has proved to be a durable vessel."
    )

# ==================================================
# PVP REPORT
# ==================================================

@bot.tree.command(name="pvp_report")
@app_commands.choices(victory=VICTORY_CHOICES)
@app_commands.describe(
    mode="PvP mode (e.g. Arena, Siege, Skirmish)"
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
    await interaction.response.defer()  # 🔥 FIX

    rites = 3 if victory.value == "Yes" else 0
    members = build_members(member1, member2, member3)

    embed = discord.Embed(title="⚔️ PvP Report", color=discord.Color.green())
    embed.add_field(name="Mode", value=mode, inline=False)
    embed.add_field(name="Victory", value=victory.value, inline=False)

    for m in members:
        user = add_rites(m, rites)

        total = user["rites"]
        gene = user["gene"]

        await update_rank(m, total)
        new_relics = await check_relics(m)

        if new_relics:
            await interaction.channel.send(
                f"🏆 {m.mention} has unlocked relic(s):\n" +
                "\n".join([f"⚜ {r}" for r in new_relics])
            )
        embed.add_field(
            name=m.display_name,
            value=f"+{rites} Rites\nTotal: {total}\n{get_progress_text(total)}",
            inline=False
        )

    screenshots = [screenshot1, screenshot2, screenshot3, screenshot4]
    screenshots = [s for s in screenshots if s]

    await send_gallery(interaction, embed, screenshots)

    await interaction.followup.send(
        "... [Combat efficiency confirmed. Daemonium containment holding [IN PROGRESS]. Data-transfer complete.]"
    )

# ==================================================
# READY
# ==================================================
@bot.tree.command(name="relic_progress", description="View relic unlock progression for a member")
async def relic_progress(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user

    data = load_data()
    user = ensure_user(data["members"].get(str(member.id), {}))

    rites = user["rites"]
    gene = user["gene"]
    unlocked = user.get("relics", [])

    embed = discord.Embed(
        title="🧬 Relic Progression",
        description=f"Tracking relic unlock status for **{member.display_name}**",
        color=discord.Color.dark_purple()
    )

    for relic, req in RELICS.items():
        status = "✅ UNLOCKED" if relic in unlocked else "🔒 LOCKED"

        embed.add_field(
            name=f"{relic} — {status}",
            value=(
                f"Gene Seeds: {gene}/{req['gene']}\n"
                f"Rites: {rites}/{req['rites']}"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(
    name="challenge_progress",
    description="View challenge progression for a member"
)
async def challenge_progress(interaction: discord.Interaction, member: discord.Member = None):

    member = member or interaction.user

    data = load_data()
    user = ensure_user(data["members"].get(str(member.id), {}))

    rites = user["rites"]
    completed = user.get("completed_challenges", [])

    days = (
        datetime.now(timezone.utc) - member.joined_at
    ).days if member.joined_at else 0

    embed = discord.Embed(
        title="📜 Challenge Progression",
        description=f"Tracking challenge status for **{member.display_name}**",
        color=discord.Color.dark_gold()
    )

    for challenge_name, req in CHALLENGE_REQUIREMENTS.items():

        emoji = CHALLENGES.get(challenge_name, {}).get("emoji", "")
        auto = CHALLENGES.get(challenge_name, {}).get("auto", False)

        status = "🔒 Locked"
        if challenge_name in completed:
            status = "✅ Completed"

        # -------------------------
        # REQUIREMENT BUILD
        # -------------------------
        lines = []

        if "rites" in req:
            lines.append(f"Rites: {rites}/{req['rites']}")

        if "days" in req:
            lines.append(f"Time: {days}/{req['days']} days")

        if req.get("approval"):
            lines.append("Officer Approval Required")

        if "special" in req:
            lines.append(f"⚠ {req['special']}")

        # -------------------------
        # DEPENDENCY CHECKS
        # -------------------------

        if challenge_name == "Veteran" and days < 30:
            status = "🔒 Locked (Time Requirement)"

        if challenge_name == "Enochian Guard":
            if "Veteran" not in completed:
                status = "🔒 Locked (Requires Veteran)"

        if challenge_name == "Daemonium Palatinae":
            if "Enochian Guard" not in completed:
                status = "🔒 Locked (Requires Enochian Guard)"

        # -------------------------
        # FINAL DISPLAY
        # -------------------------

        embed.add_field(
            name=f"{emoji} {challenge_name} — {status}",
            value=f"Type: {'Auto' if auto else 'Officer Approval'}\n"
                  + ("\n".join(lines) if lines else "No requirements listed"),
            inline=False
        )

    await interaction.response.send_message(embed=embed)

synced = False

@bot.event
async def on_ready():
    global synced
    if not synced:
        await bot.tree.sync()
        synced = True
    print(f"Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    channel = member.guild.get_channel(1500628323863101631)

    if channel:
        await channel.send(
            f"⚔️ **INITIATE DETECTED** ⚔️\n\n"
            f"Welcome to Banish, home of the Exorcists!\n"
            f"I am the Techsorcist, keeper of your records.\n\n"
            f"Proceed to the Hall of Tempering to begin your trials, {member.mention}."
        )
        
keep_alive()
bot.run(TOKEN)
