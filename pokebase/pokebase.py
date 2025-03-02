import asyncio
import base64
import random
from contextlib import suppress
from io import BytesIO
from math import floor
from string import capwords

import aiohttp
import discord
import jmespath
from aiocache import SimpleMemoryCache, cached
from bs4 import BeautifulSoup as bsp
from PIL import Image

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.chat_formatting import bold, humanize_number, inline, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

cache = SimpleMemoryCache()

API_URL = "https://pokeapi.co/api/v2"


class Pokebase(commands.Cog):
    """Search for various info about a Pokémon and related data."""

    __authors__ = "phalt", "ow0x"
    __version__ = "0.4.1"

    def format_help_for_context(self, ctx: Context) -> str:
        """Thanks Sinbad!"""
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nAuthors: {self.__authors__}\nCog Version: {self.__version__}"

    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.intro_gen = ["na", "rb", "gs", "rs", "dp", "bw", "xy", "sm", "ss"]
        self.intro_games = {
            "na": "Unknown",
            "rb": "Red/Blue\n(Gen. 1)",
            "gs": "Gold/Silver\n(Gen. 2)",
            "rs": "Ruby/Sapphire\n(Gen. 3)",
            "dp": "Diamond/Pearl\n(Gen. 4)",
            "bw": "Black/White\n(Gen. 5)",
            "xy": "X/Y\n(Gen. 6)",
            "sm": "Sun/Moon\n(Gen. 7)",
            "ss": "Sword/Shield\n(Gen. 8)",
        }
        self.styles = {
            "default": 3,
            "black": 50,
            "collector": 96,
            "dp": 5,
            "purple": 43,
        }
        self.trainers = {
            "ash": 13,
            "red": 922,
            "ethan": 900,
            "lyra": 901,
            "brendan": 241,
            "may": 255,
            "lucas": 747,
            "dawn": 856,
        }
        self.badges = {
            "kanto": [2, 3, 4, 5, 6, 7, 8, 9],
            "johto": [10, 11, 12, 13, 14, 15, 16, 17],
            "hoenn": [18, 19, 20, 21, 22, 23, 24, 25],
            "sinnoh": [26, 27, 28, 29, 30, 31, 32, 33],
            "unova": [34, 35, 36, 37, 38, 39, 40, 41],
            "kalos": [44, 45, 46, 47, 48, 49, 50, 51],
        }

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    def get_generation(self, pkmn_id: int):
        if pkmn_id > 898:
            return 0
        elif pkmn_id >= 810:
            return 8
        elif pkmn_id >= 722:
            return 7
        elif pkmn_id >= 650:
            return 6
        elif pkmn_id >= 494:
            return 5
        elif pkmn_id >= 387:
            return 4
        elif pkmn_id >= 252:
            return 3
        elif pkmn_id >= 152:
            return 2
        elif pkmn_id >= 1:
            return 1
        else:
            return 0

    @cached(ttl=86400, cache=SimpleMemoryCache)
    async def get_pokemon_data(self, pokemon: str):
        try:
            async with self.session.get(API_URL + f"/pokemon/{pokemon.lower()}") as response:
                if response.status != 200:
                    return None
                pokemon_data = await response.json()
                return pokemon_data
        except asyncio.TimeoutError:
            return None

    @cached(ttl=86400, cache=SimpleMemoryCache)
    async def get_species_data(self, pkmn_id: int):
        try:
            async with self.session.get(API_URL + f"/pokemon-species/{pkmn_id}") as response:
                if response.status != 200:
                    return None
                species_data = await response.json()
        except asyncio.TimeoutError:
            return None

        return species_data

    @cached(ttl=86400, cache=SimpleMemoryCache)
    async def get_evolution_chain(self, evo_url: str):
        try:
            async with self.session.get(evo_url) as response:
                if response.status != 200:
                    return None
                evolution_data = await response.json()
        except asyncio.TimeoutError:
            return None

        return evolution_data

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def pdex(self, ctx: Context, *, pokemon: str):
        """Search for various info about a Pokémon.

        You can search by name or ID of a Pokémon.
        Pokémon ID refers to National Pokédex number.
        https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_by_National_Pok%C3%A9dex_number
        """
        pokemon = pokemon.replace(" ", "-")
        async with ctx.typing():
            data = await self.get_pokemon_data(pokemon)
            if not data:
                return await ctx.send("No results.")

            embed = discord.Embed(colour=await ctx.embed_colour())
            embed.set_thumbnail(
                url=f"https://assets.pokemon.com/assets/cms2/img/pokedex/full/{str(data.get('id')).zfill(3)}.png",
            )
            introduced_in = str(
                self.intro_games[self.intro_gen[self.get_generation(data.get("id", 0))]]
            )
            embed.add_field(name="Introduced In", value=introduced_in)
            humanize_height = (
                f"{floor(data.get('height', 0) * 3.94 // 12)} ft. "
                + f"{floor(data.get('height', 0) * 3.94 % 12)} in."
                + f"\n({data.get('height') / 10} m.)"
            )
            embed.add_field(name="Height", value=humanize_height)
            humanize_weight = (
                f"{round(data.get('weight', 0) * 0.2205, 2)} lbs."
                + f"\n({data.get('weight') / 10} kgs.)"
            )
            embed.add_field(name="Weight", value=humanize_weight)
            embed.add_field(
                name="Types",
                value="/".join(x.get("type").get("name").title() for x in data.get("types")),
            )

            pokemon_name = data.get("name", "none").title()
            species_data = await self.get_species_data(data.get("id"))
            if species_data:
                with suppress(IndexError):
                    pokemon_name = [
                        x["name"] for x in species_data["names"]
                        if x["language"]["name"] == "en"
                    ][0]

                gender_rate = species_data.get("gender_rate")
                male_ratio = 100 - ((gender_rate / 8) * 100)
                female_ratio = (gender_rate / 8) * 100
                genders = {
                    "male": 0.0 if gender_rate == -1 else male_ratio,
                    "female": 0.0 if gender_rate == -1 else female_ratio,
                    "genderless": True if gender_rate == -1 else False,
                }
                final_gender_rate = ""
                if genders["genderless"]:
                    final_gender_rate += "Genderless"
                if genders["male"] != 0.0:
                    final_gender_rate += f"♂️ {genders['male']}%\n"
                if genders["female"] != 0.0:
                    final_gender_rate += f"♀️ {genders['female']}%"
                embed.add_field(name="Gender Rate", value=final_gender_rate)
                embed.add_field(
                    name="Base Happiness",
                    value=f"{species_data.get('base_happiness', 0)} / 255",
                )
                embed.add_field(
                    name="Capture Rate",
                    value=f"{species_data.get('capture_rate', 0)} / 255",
                )

                genus = [
                    x.get("genus")
                    for x in species_data.get("genera")
                    if x.get("language").get("name") == "en"
                ]
                genus_text = "The " + genus[0]
                flavor_text = [
                    x.get("flavor_text")
                    for x in species_data.get("flavor_text_entries")
                    if x.get("language").get("name") == "en"
                ]
                flavor_text = (
                    random.choice(flavor_text).replace("\n", " ").replace("\f", " ")
                    .replace("\r", " ")
                )
                flavor_text = flavor_text
                embed.description = f"**{genus_text}**\n\n{flavor_text}"

            if data.get("held_items"):
                held_items = ""
                for item in data.get("held_items"):
                    held_items += "{} ({}%)\n".format(
                        item.get("item").get("name").replace("-", " ").title(),
                        item.get("version_details")[0].get("rarity"),
                    )
                embed.add_field(name="Held Items", value=held_items)
            else:
                embed.add_field(name="Held Items", value="None")

            abilities = ""
            for ability in data.get("abilities"):
                abilities += (
                    "[{}](https://bulbapedia.bulbagarden.net/wiki/{}_%28Ability%29){}\n".format(
                        ability.get("ability").get("name").replace("-", " ").title(),
                        ability.get("ability").get("name").title().replace("-", "_"),
                        " (Hidden Ability)" if ability.get("is_hidden") else "",
                    )
                )

            embed.add_field(name="Abilities", value=abilities)

            base_stats = {}
            for stat in data.get("stats"):
                base_stats[stat.get("stat").get("name")] = stat.get("base_stat")
            total_base_stats = sum(base_stats.values())

            def multi_bar(attribute: str):
                return round((base_stats[attribute] / 255) * 10) * 2

            def draw_bar(attribute: str):
                fill = "█" * multi_bar(attribute)
                blank = " " * (20 - multi_bar(attribute))
                return f"`|{fill}{blank}|`"

            sp_attack = base_stats["special-attack"]
            sp_defense = base_stats["special-defense"]

            pretty_base_stats = (
                f"**`{'HP':<12}:`**  {draw_bar('hp')} **{base_stats['hp']}**\n"
                f"**`{'Attack':<12}:`**  {draw_bar('attack')} **{base_stats['attack']}**\n"
                f"**`{'Defense':<12}:`**  {draw_bar('defense')} **{base_stats['defense']}**\n"
                f"**`{'Sp. Attack':<12}:`**  {draw_bar('special-attack')} **{sp_attack}**\n"
                f"**`{'Sp. Defense':<12}:`**  {draw_bar('special-defense')} **{sp_defense}**\n"
                f"**`{'Speed':<12}:`**  {draw_bar('speed')} **{base_stats['speed']}**\n"
                f"**`{'Total':<12}:`**  `|--------------------|` **{total_base_stats}**"
            )
            embed.add_field(name="Base Stats (Base Form)", value=pretty_base_stats, inline=False)

            if species_data and species_data.get("evolution_chain"):
                evo_url = species_data.get("evolution_chain").get("url")
                evo_data = (await self.get_evolution_chain(evo_url)).get("chain")
                base_evo = evo_data["species"].get("name").title()
                evolves_to = ""
                if evo_data.get("evolves_to"):
                    evolves_to += " -> " + "/".join(
                        x["species"].get("name").title() for x in evo_data["evolves_to"]
                    )
                if evo_data.get("evolves_to") and evo_data["evolves_to"][0].get("evolves_to"):
                    evolves_to += " -> " + "/".join(
                        x["species"].get("name").title()
                        for x in evo_data["evolves_to"][0].get("evolves_to")
                    )
                if evolves_to != "":
                    embed.add_field(
                        name="Evolution Chain",
                        value=f"{base_evo} {evolves_to}",
                        inline=False,
                    )

            embed.set_author(
                name=f"#{str(data.get('id')).zfill(3)} - {pokemon_name}",
                url=f"https://www.pokemon.com/us/pokedex/{data.get('name')}",
            )

            type_effectiveness = (
                "[See it on Bulbapedia](https://bulbapedia.bulbagarden.net/wiki/"
                + f"{pokemon_name.replace(' ', '_')}_%28Pokémon%29#Type_effectiveness)"
            )
            embed.add_field(name="Weakness/Resistance", value=type_effectiveness)
            embed.set_footer(text="Powered by Poke API")

        await ctx.send(embed=embed)

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def ability(self, ctx: Context, *, ability: str):
        """Get various info about a known Pokémon ability.
        You can search by ability's name or it's unique ID.

        Abilities provide passive effects for Pokémon in battle or in the overworld.
        Pokémon have multiple possible abilities but can have only one ability at a time.
        Check out Bulbapedia for greater detail:
        http://bulbapedia.bulbagarden.net/wiki/Ability
        https://bulbapedia.bulbagarden.net/wiki/Ability#List_of_Abilities
        """
        async with ctx.typing():
            try:
                async with self.session.get(
                    API_URL + f"/ability/{ability.replace(' ', '-').lower()}/"
                ) as response:
                    if response.status != 200:
                        await ctx.send(f"https://http.cat/{response.status}")
                        return
                    data = await response.json()
            except asyncio.TimeoutError:
                return await ctx.send("Operation timed out.")

            embed = discord.Embed(colour=discord.Color.random())
            embed.title = data.get("name").replace("-", " ").title()
            embed.url = "https://bulbapedia.bulbagarden.net/wiki/{}_%28Ability%29".format(
                data.get("name").title().replace("-", "_")
            )
            embed.description = [
                x.get("effect")
                for x in data.get("effect_entries")
                if x.get("language").get("name") == "en"
            ][0]

            if data.get("generation"):
                embed.add_field(
                    name="Introduced In",
                    value="Gen. "
                    + bold(str(data.get("generation").get("name").split("-")[1].upper())),
                )
            short_effect = [
                x.get("short_effect")
                for x in data.get("effect_entries")
                if x.get("language").get("name") == "en"
            ][0]
            embed.add_field(name="Ability's Effect", value=short_effect, inline=False)
            if data.get("pokemon"):
                pokemons = ", ".join(
                    x.get("pokemon").get("name").title() for x in data.get("pokemon")
                )
                embed.add_field(
                    name=f"Pokémons with {data.get('name').title()}",
                    value=pokemons,
                    inline=False,
                )
            embed.set_footer(text="Powered by Poke API")

        await ctx.send(embed=embed)

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def moves(self, ctx: Context, pokemon: str):
        """Get the list of all possible moves a Pokémon has."""
        async with ctx.typing():
            data = await self.get_pokemon_data(pokemon)
            if not data:
                return await ctx.send("No results.")

            if not data.get("moves"):
                return await ctx.send("No moves found for this Pokémon.")

            moves_list = ""
            for i, move in enumerate(data["moves"]):
                moves_list += "`[{}]` **{}**\n".format(
                    str(i + 1).zfill(2),
                    move["move"]["name"].title().replace("-", " "),
                )

            pages = []
            for page in pagify(moves_list, delims=["\n"], page_length=400):
                embed = discord.Embed(colour=await ctx.embed_colour())
                embed.title = f"Moves for : {data['name'].title()} (#{str(data['id']).zfill(3)})"
                embed.set_thumbnail(
                    url=f"https://assets.pokemon.com/assets/cms2/img/pokedex/full/{str(data['id']).zfill(3)}.png",
                )
                embed.description = page
                pages.append(embed)

        await menu(ctx, pages, DEFAULT_CONTROLS, timeout=60.0)

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def moveinfo(self, ctx: Context, *, move: str):
        """Get various info about a Pokémon's move.
        You can search by a move name or it's ID.

        Moves are the skills of Pokémon in battle.
        In battle, a Pokémon uses one move each turn.
        Some moves (including those learned by Hidden Machine) can be used outside of battle as well,
        usually for the purpose of removing obstacles or exploring new areas.

        You can find a list of known Pokémon moves here:
        https://bulbapedia.bulbagarden.net/wiki/List_of_moves
        """
        move_query = move.replace(",", " ").replace(" ", "-").replace("'", "").lower()
        async with ctx.typing():
            try:
                async with self.session.get(API_URL + f"/move/{move_query}/") as response:
                    if response.status != 200:
                        await ctx.send(f"https://http.cat/{response.status}")
                        return
                    data = await response.json()
            except asyncio.TimeoutError:
                return await ctx.send("Operation timed out.")

            embed = discord.Embed(colour=discord.Color.random())
            embed.title = data.get("name").replace("-", " ").title()
            embed.url = "https://bulbapedia.bulbagarden.net/wiki/{}_%28move%29".format(
                capwords(move).replace(" ", "_")
            )
            if data.get("effect_entries"):
                effect = "\n".join(
                    [
                        f"{x.get('short_effect')}\n{x.get('effect')}"
                        for x in data.get("effect_entries")
                        if x.get("language").get("name") == "en"
                    ]
                )
                embed.description = f"**Move Effect:** \n\n{effect}"

            if data.get("generation"):
                embed.add_field(
                    name="Introduced In",
                    value="Gen. "
                    + bold(str(data.get("generation").get("name").split("-")[1].upper())),
                )
            if data.get("accuracy"):
                embed.add_field(name="Accuracy", value=f"{data.get('accuracy')}%")
            embed.add_field(name="Base Power", value=str(data.get("power")))
            if data.get("effect_chance"):
                embed.add_field(name="Effect Chance", value=f"{data.get('effect_chance')}%")
            embed.add_field(name="Power Points (PP)", value=str(data.get("pp")))
            if data.get("type"):
                embed.add_field(name="Move Type", value=data.get("type").get("name").title())
            if data.get("contest_type"):
                embed.add_field(
                    name="Contest Type",
                    value=data.get("contest_type").get("name").title(),
                )
            if data.get("damage_class"):
                embed.add_field(
                    name="Damage Class",
                    value=data.get("damage_class").get("name").title(),
                )
            embed.add_field(name="\u200b", value="\u200b")
            if data.get("learned_by_pokemon"):
                learned_by = [x.get("name").title() for x in data.get("learned_by_pokemon")]
                embed.add_field(
                    name=f"Learned by {str(len(learned_by))} Pokémons",
                    value=", ".join(learned_by)[:500] + "... and more.",
                    inline=False,
                )
            embed.set_footer(text="Powered by Poke API")

        await ctx.send(embed=embed)

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def trainercard(
        self,
        ctx: Context,
        name: str,
        style: str,
        trainer: str,
        badge: str,
        *,
        pokemons: str,
    ):
        """Generate a trainer card for a Pokémon trainer in different styles.

        This command requires you to pass values for multiple parameters.
        These parameters are explained briefly as follows:

        `name` - Provide any personalised name of your choice.
        `style` - Only `default`, `black`, `collector`, `dp`, `purple` styles are supported.
        `trainer` - `ash`, `red`, `ethan`, `lyra`, `brendan`, `may`, `lucas`, `dawn` are supported.
        `badge` - `kanto`, `johto`, `hoenn`, `sinnoh`, `unova` and `kalos`  badge leagues are supported.
        `pokemons` - You can provide maximum up to 6 Pokémon's names or IDs.
        (Pokémons from #891 to #898 are not supported yet for trainer card)
        """
        base_url = "https://pokecharms.com/index.php?trainer-card-maker/render"
        if style.lower() not in ["default", "black", "collector", "dp", "purple"]:
            return await ctx.send_help()
        if trainer.lower() not in [
            "ash",
            "red",
            "ethan",
            "lyra",
            "brendan",
            "may",
            "lucas",
            "dawn",
        ]:
            return await ctx.send_help()
        if badge.lower() not in ["kanto", "johto", "hoenn", "sinnoh", "unova", "kalos"]:
            return await ctx.send_help()
        if len(pokemons.split()) > 6:
            return await ctx.send_help()

        async with ctx.typing():
            pkmn_ids = []
            for pokemon in pokemons.split():
                get_ids = await self.get_pokemon_data(pokemon)
                if get_ids.get("id"):
                    pkmn_ids.append(get_ids["id"])

            panel_ids = []
            for npn in pkmn_ids:
                panel_url = "https://pokecharms.com/trainer-card-maker/pokemon-panels"
                payload = aiohttp.FormData()
                payload.add_field("number", npn)
                payload.add_field("_xfResponseType", "json")
                async with self.session.post(panel_url, data=payload) as resp:
                    if resp.status != 200:
                        panel_ids.append("1")
                    soup = bsp((await resp.json()).get("templateHtml"), "html.parser")
                    try:
                        panel_ids.append(soup.find_all("li")[0].get("data-id"))
                    except IndexError:
                        panel_ids.append("1")

            form = aiohttp.FormData()
            form.add_field("trainername", name[:12])
            form.add_field("background", str(self.styles[style.lower()]))
            form.add_field("character", str(self.trainers[trainer.lower()]))
            form.add_field("badges", "8")
            form.add_field("badgesUsed", ",".join(str(x) for x in self.badges[badge.lower()]))
            form.add_field("pokemon", str(len(pokemons.split())))
            form.add_field("pokemonUsed", ",".join(panel_ids))
            form.add_field("_xfResponseType", "json")
            try:
                async with self.session.post(base_url, data=form) as response:
                    if response.status != 200:
                        return await ctx.send(f"https://http.cat/{response.status}")
                    output = (await response.json()).get("trainerCard")
            except asyncio.TimeoutError:
                return await ctx.send("Operation timed out.")

        if output:
            base64_img_bytes = output.encode("utf-8")
            decoded_image_data = BytesIO(base64.decodebytes(base64_img_bytes))
            decoded_image_data.seek(0)
            await ctx.send(file=discord.File(decoded_image_data, "trainer-card.png"))
            return
        else:
            await ctx.send("No trainer card was generated. :(")

    @cached(ttl=86400, cache=SimpleMemoryCache)
    async def get_json(self, query_url: str):
        try:
            async with self.session.get(query_url) as response:
                if response.status != 200:
                    return None
                item_data = await response.json()
        except asyncio.TimeoutError:
            return None

        return item_data

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def item(self, ctx: Context, *, item: str):
        """Get various info about a Pokémon item.
        You can search by an item's name or unique ID.

        An item is an object in the games which the player can pick up,
        keep in their bag, and use in some manner.
        They have various uses, including healing, powering up,
        helping catch Pokémon, or to access a new area. For more info:
        https://bulbapedia.bulbagarden.net/wiki/Item
        https://bulbapedia.bulbagarden.net/wiki/Category:Items
        """
        item = item.replace(" ", "-").lower()
        async with ctx.typing():
            embed = discord.Embed(colour=await ctx.embed_colour())
            item_query_url = f"https://pokeapi.co/api/v2/item/{item}"
            item_data = await self.get_json(item_query_url)
            if not item_data:
                return await ctx.send("No results.")

            embed.title = item_data.get("name").title().replace("-", " ")
            embed.url = "https://bulbapedia.bulbagarden.net/wiki/{}".format(
                item.title().replace("-", "_")
            )
            item_effect = (
                "**Item effect:** "
                + [
                    x.get("effect")
                    for x in item_data.get("effect_entries")
                    if x.get("language").get("name") == "en"
                ][0]
            )
            item_summary = (
                "**Summary:** "
                + [
                    x.get("short_effect")
                    for x in item_data.get("effect_entries")
                    if x.get("language").get("name") == "en"
                ][0]
            )
            embed.description = f"{item_effect}\n\n{item_summary}"
            embed.add_field(name="Cost", value=humanize_number(item_data.get("cost")))
            embed.add_field(
                name="Category",
                value=str(
                    item_data.get("category").get("name", "unknown").title().replace("-", " ")
                ),
            )
            if item_data.get("attributes"):
                attributes = "\n".join(
                    x.get("name").title().replace("-", " ") for x in item_data["attributes"]
                )
                embed.add_field(name="Attributes", value=attributes)
            if item_data.get("fling_power"):
                embed.add_field(name="Fling Power", value=humanize_number(item_data["fling_power"]))
            if item_data.get("fling_effect"):
                fling_data = await self.get_json(item_data["fling_effect"]["url"])
                if fling_data:
                    fling_effect = [
                        x.get("effect")
                        for x in fling_data.get("effect_entries")
                        if x.get("language").get("name") == "en"
                    ][0]
                    embed.add_field(name="Fling Effect", value=fling_effect, inline=False)
            if item_data.get("held_by_pokemon"):
                held_by = ", ".join(
                    x.get("pokemon").get("name").title() for x in item_data["held_by_pokemon"]
                )
                embed.add_field(name="Held by Pokémon(s)", value=held_by, inline=False)
            embed.set_footer(text="Powered by Poke API!")

        await ctx.send(embed=embed)

    @commands.command(name="itemcat")
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    async def item_category(self, ctx: Context, *, category: str):
        """Returns the list of items in a given Pokémon item category."""
        category = category.replace(" ", "-").lower()
        async with ctx.typing():
            category_data = await self.get_json(
                f"https://pokeapi.co/api/v2/item-category/{category}/"
            )
            if not category_data:
                return await ctx.send("No results.")
            embed = discord.Embed(colour=await ctx.embed_colour())
            embed.title = f"{category_data['name'].title().replace('-', ' ')}"
            items_list = ""
            for count, item in enumerate(category_data.get("items")):
                items_list += "**{}.** {}\n".format(
                    count + 1, item.get("name").title().replace("-", " ")
                )

            embed.description = "__**List of items in this category:**__\n\n" + items_list
            embed.set_footer(text="Powered by Poke API!")

        await ctx.send(embed=embed)

    @commands.command()
    @cached(ttl=86400, cache=SimpleMemoryCache)
    @commands.bot_has_permissions(embed_links=True)
    async def location(self, ctx: Context, pokemon: str):
        """Responds with the location data for a Pokémon."""
        async with ctx.typing():
            data = await self.get_pokemon_data(pokemon)
            if not (data and data.get("location_area_encounters")):
                return await ctx.send("No location data found for said Pokémon.")

            get_encounters = await self.get_json(data["location_area_encounters"])
            if not get_encounters:
                return await ctx.send("No location data found for this Pokémon.")

            jquery = jmespath.compile(
                "[*].{url: location_area.url, name: version_details[*].version.name}"
            )
            new_dict = jquery.search(get_encounters)

            pretty_data = ""
            for i, loc in enumerate(new_dict):
                area_data = await self.get_json(loc["url"])
                location_data = await self.get_json(area_data["location"]["url"])
                location_names = ", ".join(
                    x["name"] for x in location_data["names"] if x["language"]["name"] == "en"
                )
                generations = "/".join(x.title().replace("-", " ") for x in loc["name"])
                pretty_data += f"`[{str(i + 1).zfill(2)}]` {bold(location_names)} ({generations})\n"

            embed = discord.Embed(colour=await ctx.embed_colour())
            embed.title = f"#{str(data['id']).zfill(3)} - {data['name'].title()}"
            embed.url = f"https://bulbapedia.bulbagarden.net/wiki/{data['name'].title()}_%28Pok%C3%A9mon%29#Game_locations"
            embed.set_thumbnail(
                url=f"https://assets.pokemon.com/assets/cms2/img/pokedex/full/{str(data['id']).zfill(3)}.png",
            )
            embed.description = pretty_data

        await ctx.send(embed=embed)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def tcgcard(self, ctx: commands.Context, *, query: str):
        """Fetch Pokémon cards based on Pokémon Trading Card Game (a.k.a Pokémon TCG)."""
        api_key = (await ctx.bot.get_shared_api_tokens("pokemontcg")).get("api_key")
        if api_key:
            headers = {"X-Api-Key": api_key}
        else:
            headers = None

        await ctx.trigger_typing()
        base_url = f"https://api.pokemontcg.io/v2/cards?q=name:{query}"
        try:
            async with self.session.get(base_url, headers=headers) as response:
                if response.status != 200:
                    await ctx.send(f"https://http.cat/{response.status}")
                    return
                output = await response.json()
        except asyncio.TimeoutError:
            return await ctx.send("Operation timed out.")

        if not output["data"]:
            return await ctx.send("No results.")

        pages = []
        for i, data in enumerate(output["data"]):
            embed = discord.Embed(colour=await ctx.embed_colour())
            embed.title = data["name"]
            embed.description = "**Rarity:** " + str(data.get("rarity"))
            embed.add_field(name="Artist:", value=str(data.get("artist")))
            embed.add_field(name="Belongs to Set:", value=str(data["set"]["name"]), inline=False)
            embed.add_field(name="Set Release Date:", value=str(data["set"]["releaseDate"]))
            embed.set_thumbnail(url=str(data["set"]["images"]["logo"]))
            embed.set_image(url=str(data["images"]["large"]))
            embed.set_footer(
                text=f"Page {i + 1} of {len(output['data'])} | Powered by Pokémon TCG API!"
            )
            pages.append(embed)

        if len(pages) == 1:
            await ctx.send(embed=pages[0])
            return
        else:
            await menu(ctx, pages, DEFAULT_CONTROLS, timeout=60.0)

    async def get_pokemon_image(self, url: str):
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                data = await response.read()
                # data.seek(0)
                return BytesIO(data)
        except asyncio.TimeoutError:
            return None

    async def generate_image(self, poke_id, hide: bool):
        base_image = Image.open(bundled_data_path(self) / "template.png")
        bg_width, bg_height = base_image.size

        base_url = f"https://assets.pokemon.com/assets/cms2/img/pokedex/full/{poke_id}.png"
        pbytes = await self.get_pokemon_image(base_url)
        # if pbytes is None:
        #     return None

        poke_image = Image.open(pbytes)

        poke_width, poke_height = poke_image.size

        poke_image_resized = poke_image.resize((int(poke_width * 1.6), int(poke_height * 1.6)))

        if hide:
            p_load = poke_image_resized.load()
            for y in range(poke_image_resized.size[1]):
                for x in range(poke_image_resized.size[0]):
                    if p_load[x, y] == (0, 0, 0, 0):
                        continue
                    else:
                        p_load[x, y] = (1, 1, 1)

        paste_w = int((bg_width - poke_width) / 10)
        paste_h = int((bg_height - poke_height) / 4)

        base_image.paste(poke_image_resized, (paste_w, paste_h), poke_image_resized)

        temp = BytesIO()
        base_image.save(temp, "png")
        temp.seek(0)
        pbytes.close()
        base_image.close()
        poke_image.close()
        return temp

    @commands.command(aliases=["wtp"])
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(1, commands.BucketType.channel)
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def whosthatpokemon(self, ctx: commands.Context, generation: str = None):
        """Guess Who's that Pokémon within 15 seconds!

        You can optionally specify generation from `gen1` to `gen8` only,
        to restrict this guessing game to specific Pokemon generation.

        Otherwise, it will default to pulling random pokemon from all 8 Gens.
        """
        allowed_gens = ["gen1", "gen2", "gen3", "gen4", "gen5", "gen6", "gen7", "gen8"]
        if generation and generation not in allowed_gens:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"Only {', '.join(inline(x) for x in allowed_gens)} generations are allowed."
            )

        if generation == "gen1":
            poke_id = random.randint(1, 151)
        elif generation == "gen2":
            poke_id = random.randint(152, 251)
        elif generation == "gen3":
            poke_id = random.randint(252, 386)
        elif generation == "gen4":
            poke_id = random.randint(387, 493)
        elif generation == "gen5":
            poke_id = random.randint(494, 649)
        elif generation == "gen6":
            poke_id = random.randint(650, 721)
        elif generation == "gen7":
            poke_id = random.randint(722, 809)
        elif generation == "gen8":
            poke_id = random.randint(810, 898)
        else:
            poke_id = random.randint(1, 898)

        await ctx.channel.trigger_typing()
        temp = await self.generate_image(str(poke_id).zfill(3), True)
        initial_img = discord.File(temp, "whosthatpokemon.png")
        message = await ctx.reply(
            embed=discord.Embed(
                title="You have __**15** seconds__ to answer. Who's that Pokémon?",
                colour=await ctx.embed_colour(),
            ).set_image(url="attachment://whosthatpokemon.png"),
            file=initial_img,
            mention_author=False,
        )

        names_data = (await self.get_species_data(poke_id)).get("names")
        eligible_names = [x["name"].lower() for x in names_data]
        english_name = [x["name"] for x in names_data if x["language"]["name"] == "en"][0]

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            answer = await self.bot.wait_for("message", check=check, timeout=15.0)
        except asyncio.TimeoutError:
            with suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                await message.delete()
            return await ctx.send(
                f"Time over! **{ctx.author}** did not guess the Pokémon within 15 seconds."
            )

        revealed = await self.generate_image(str(poke_id).zfill(3), False)
        img = discord.File(revealed, "whosthatpokemon.png")
        if answer and answer.content.lower() not in eligible_names:
            with suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                await message.delete()
            emb = discord.Embed(
                title="Your guess is very wrong! 😔 😮\u200d💨",
                colour=0xFF0000,
            )
            emb.description = f"It was ... **{english_name}**"
            emb.set_image(url="attachment://whosthatpokemon.png")
            emb.set_footer(text=f"Requested by {ctx.author}", icon_url=str(ctx.author.avatar_url))
            return await ctx.channel.send(embed=emb, file=img)
        else:
            with suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                await message.delete()
            emb = discord.Embed(title="🎉 POGGERS!! You guessed it right! 🎉", colour=0x00FF00)
            emb.description = f"It was ... **{english_name}**"
            emb.set_image(url=f"attachment://whosthatpokemon.png")
            emb.set_footer(text=f"Requested by {ctx.author}", icon_url=str(ctx.author.avatar_url))
            return await ctx.channel.send(embed=emb, file=img)
