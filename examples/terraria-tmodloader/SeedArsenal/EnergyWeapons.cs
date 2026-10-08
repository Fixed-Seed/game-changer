using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.Audio;
using Terraria.DataStructures;
using Terraria.Graphics.CameraModifiers;
using Terraria.ID;
using Terraria.ModLoader;

namespace SeedArsenal
{
	// ------------------------------------------------------------------ Tesla Rifle: chain lightning

	public class TeslaRifle : ModItem
	{
		public override string Texture => "SeedArsenal/Assets/TeslaRifle";

		public override void SetDefaults()
		{
			Item.width = 62; Item.height = 30;
			Item.useStyle = ItemUseStyleID.Shoot; Item.useTime = Item.useAnimation = 13; Item.autoReuse = true;
			Item.damage = 40; Item.DamageType = DamageClass.Magic; Item.knockBack = 2f; Item.noMelee = true;
			Item.shoot = ModContent.ProjectileType<TeslaArc>(); Item.shootSpeed = 1f;
			Item.UseSound = SoundID.Item93; Item.rare = ItemRarityID.Cyan;
		}

		public override Vector2? HoldoutOffset() => new Vector2(-8, 0);

		public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
		{
			// first target: nearest enemy within 30 degrees of the aim, then hop to up to 4 more
			var aim = velocity.SafeNormalize(Vector2.UnitX);
			var muzzle = player.Center + aim * 34;
			var hit = new HashSet<int>();
			var first = Fx.Nearest(muzzle, 800, n => Vector2.Dot((n.Center - muzzle).SafeNormalize(aim), aim) > 0.86f);
			var from = muzzle;
			if (first == null)
			{
				Projectile.NewProjectile(source, from, Vector2.Zero, type, 0, 0, player.whoAmI, aim.X * 420, aim.Y * 420);
				return false;
			}
			var cur = first;
			float dmg = damage;
			for (int k = 0; k < 5 && cur != null; k++)
			{
				var span = cur.Center - from;
				Projectile.NewProjectile(source, from, Vector2.Zero, type, 0, 0, player.whoAmI, span.X, span.Y);
				if (player.whoAmI == Main.myPlayer) cur.SimpleStrikeNPC((int)dmg, Math.Sign(cur.Center.X - from.X), Main.rand.NextBool(8), 2f, DamageClass.Magic);
				for (int i = 0; i < 8; i++)
					Dust.NewDustPerfect(cur.Center + Main.rand.NextVector2Circular(12, 12), DustID.Electric, Main.rand.NextVector2Circular(4, 4), 0, default, 1.1f).noGravity = true;
				hit.Add(cur.whoAmI);
				from = cur.Center;
				dmg *= 0.85f;
				cur = Fx.Nearest(from, 340, n => !hit.Contains(n.whoAmI));
			}
			return false;
		}

		public override void AddRecipes() => CreateRecipe()
			.AddRecipeGroup(RecipeGroupID.IronBar, 8)
			.AddIngredient(ItemID.FallenStar, 3)
			.AddTile(TileID.Anvils)
			.Register();
	}

	/// <summary>Visual only: a flickering jagged arc from its spawn point to spawn point + (ai[0], ai[1]).
	/// The span rides in ai (not velocity) because ai is what gets synced to other players.</summary>
	public class TeslaArc : ModProjectile
	{
		public override string Texture => "SeedArsenal/Assets/HomingMissile"; // unused: drawn procedurally
		Vector2 Span => new(Projectile.ai[0], Projectile.ai[1]);

		public override void SetDefaults()
		{
			Projectile.width = Projectile.height = 4;
			Projectile.friendly = Projectile.hostile = false;
			Projectile.tileCollide = false; Projectile.timeLeft = 9; Projectile.penetrate = -1;
		}

		public override void AI() => Lighting.AddLight(Projectile.Center + Span / 2, 0.3f, 0.7f, 1.2f);

		public override bool PreDraw(ref Color lightColor)
		{
			var span = Span;
			var a = Projectile.Center;
			var b = a + span;
			var n = new Vector2(-span.Y, span.X).SafeNormalize(Vector2.Zero);
			int segs = Math.Max(3, (int)(span.Length() / 26));
			var pts = new Vector2[segs + 1];
			for (int i = 0; i <= segs; i++)
				pts[i] = Vector2.Lerp(a, b, i / (float)segs) + (i == 0 || i == segs ? Vector2.Zero : n * Main.rand.NextFloat(-16, 16));
			float fade = Projectile.timeLeft / 9f;
			Fx.Additive(true);
			for (int i = 0; i < segs; i++)
			{
				Fx.Line(pts[i], pts[i + 1], 9, new Color(60, 140, 255) * (0.5f * fade));
				Fx.Line(pts[i], pts[i + 1], 3, new Color(220, 245, 255) * fade);
			}
			Fx.Additive(false);
			return false;
		}
	}

	// ------------------------------------------------------------------ Singularity Launcher: black hole

	public class SingularityLauncher : ModItem
	{
		public override string Texture => "SeedArsenal/Assets/SingularityLauncher";

		public override void SetDefaults()
		{
			Item.width = 70; Item.height = 34;
			Item.useStyle = ItemUseStyleID.Shoot; Item.useTime = Item.useAnimation = 50; Item.autoReuse = true;
			Item.damage = 34; Item.DamageType = DamageClass.Magic; Item.noMelee = true;
			Item.shoot = ModContent.ProjectileType<SingularityOrb>(); Item.shootSpeed = 11f;
			Item.UseSound = SoundID.Item117; Item.rare = ItemRarityID.Purple;
		}

		public override Vector2? HoldoutOffset() => new Vector2(-10, 0);

		public override void AddRecipes() => CreateRecipe()
			.AddRecipeGroup(RecipeGroupID.IronBar, 8)
			.AddIngredient(ItemID.Lens, 2)
			.AddIngredient(ItemID.FallenStar, 3)
			.AddTile(TileID.Anvils)
			.Register();
	}

	public class SingularityOrb : ModProjectile
	{
		public override string Texture => "SeedArsenal/Assets/HomingMissile"; // unused: drawn procedurally
		const int Travel = 36, Hole = 150;

		public override void SetDefaults()
		{
			Projectile.width = Projectile.height = 20;
			Projectile.friendly = false; Projectile.tileCollide = false; Projectile.penetrate = -1;
			Projectile.timeLeft = Travel + Hole;
		}

		float Age => Travel + Hole - Projectile.timeLeft;
		bool Open => Age >= Travel;

		public override void AI()
		{
			var c = Projectile.Center;
			if (!Open)
			{
				Projectile.velocity *= 0.95f;
				Dust.NewDustPerfect(c, DustID.PurpleTorch, Main.rand.NextVector2Circular(1, 1), 0, default, 1.8f).noGravity = true;
				return;
			}
			Projectile.velocity = Vector2.Zero;
			if (Age == Travel) SoundEngine.PlaySound(SoundID.Item122 with { Pitch = -0.5f }, c);
			float grow = Math.Min(1f, (Age - Travel) / 20f);
			foreach (var n in Main.ActiveNPCs)
			{
				if (n.friendly || n.townNPC) continue;
				var d = c - n.Center;
				float dist = d.Length();
				if (dist > 420) continue;
				float pull = n.boss ? 0.04f : 1.1f * (1 - dist / 420) + 0.25f;
				n.velocity = n.velocity * (n.boss ? 1f : 0.9f) + d.SafeNormalize(Vector2.Zero) * pull * 3f;
				if (dist < 110 && (int)Age % 8 == 0 && Projectile.owner == Main.myPlayer)
					n.SimpleStrikeNPC(Projectile.damage / (n.boss ? 2 : 1), Math.Sign(-d.X), false, 0f, DamageClass.Magic);
			}
			// loose loot gets sucked in too
			foreach (var it in Main.ActiveItems)
				if (Vector2.Distance(it.Center, c) < 300) it.velocity += (c - it.Center).SafeNormalize(Vector2.Zero) * 0.6f;
			for (int i = 0; i < 6; i++)
			{
				var r = Main.rand.NextFloat(40, 190) * grow;
				var a = Main.rand.NextFloat(MathHelper.TwoPi);
				var pos = c + a.ToRotationVector2() * r;
				var tangent = (a + MathHelper.PiOver2).ToRotationVector2();
				Dust.NewDustPerfect(pos, i % 2 == 0 ? DustID.PurpleTorch : DustID.Shadowflame, tangent * 5 + (c - pos) * 0.06f, 0, default, 1.7f).noGravity = true;
			}
			Lighting.AddLight(c, 0.6f, 0.2f, 0.9f);
			if (Projectile.timeLeft == 1) Implode(c);
		}

		void Implode(Vector2 c)
		{
			SoundEngine.PlaySound(SoundID.Item14 with { Pitch = -0.4f }, c);
			SoundEngine.PlaySound(SoundID.Item62 with { Pitch = -0.2f }, c);
			Fx.SmallBoom(c, 2.4f);
			for (int i = 0; i < 50; i++)
				Dust.NewDustPerfect(c, DustID.PurpleTorch, Main.rand.NextVector2Circular(12, 12), 0, default, 2.4f).noGravity = true;
			Main.instance.CameraModifiers.Add(new PunchCameraModifier(c, Main.rand.NextVector2Unit(), 8f, 8f, 20, 2000f));
			if (Projectile.owner == Main.myPlayer)
				foreach (var n in Main.ActiveNPCs)
					if (!n.friendly && !n.townNPC && Vector2.Distance(n.Center, c) < 200) n.SimpleStrikeNPC(Projectile.damage * 3, Math.Sign(n.Center.X - c.X), false, 6f, DamageClass.Magic);
		}

		public override bool PreDraw(ref Color lightColor)
		{
			var c = Projectile.Center;
			var disc = Fx.DiscTexture();
			float pulse = 1 + 0.08f * MathF.Sin(Age * 0.4f);
			if (!Open)
			{
				Fx.Additive(true);
				Main.spriteBatch.Draw(disc, c - Main.screenPosition, null, new Color(190, 90, 255) * 0.9f, 0, new Vector2(12), 1.1f * pulse, SpriteEffects.None, 0);
				Fx.Additive(false);
				return false;
			}
			float grow = Math.Min(1f, (Age - Travel) / 20f);
			float shrink = Math.Min(1f, Projectile.timeLeft / 12f);
			float s = grow * shrink;
			Fx.Additive(true);
			Main.spriteBatch.Draw(disc, c - Main.screenPosition, null, new Color(150, 60, 255) * 0.55f, 0, new Vector2(12), 7.5f * s * pulse, SpriteEffects.None, 0);
			Main.spriteBatch.Draw(disc, c - Main.screenPosition, null, new Color(255, 170, 255) * 0.7f, 0, new Vector2(12), 4.6f * s * pulse, SpriteEffects.None, 0);
			Fx.Additive(false);
			Main.spriteBatch.Draw(disc, c - Main.screenPosition, null, Color.Black, 0, new Vector2(12), 3.6f * s, SpriteEffects.None, 0);
			return false;
		}
	}

	// ------------------------------------------------------------------ Orbital Strike: sky beam

	public class OrbitalStrike : ModItem
	{
		public override string Texture => "SeedArsenal/Assets/OrbitalStrike";

		public override void SetDefaults()
		{
			Item.width = 24; Item.height = 38;
			Item.useStyle = ItemUseStyleID.HoldUp; Item.useTime = Item.useAnimation = 40;
			Item.damage = 160; Item.DamageType = DamageClass.Magic; Item.noMelee = true;
			Item.UseSound = SoundID.Item113; Item.rare = ItemRarityID.Red;
		}

		public override bool? UseItem(Player player)
		{
			if (player.whoAmI != Main.myPlayer || player.ownedProjectileCounts[ModContent.ProjectileType<OrbitalBeam>()] > 0) return true;
			var target = Fx.Nearest(Main.MouseWorld, 900, n => n.boss) ?? Fx.Nearest(Main.MouseWorld, 900);
			float x = target?.Center.X ?? Main.MouseWorld.X;
			Projectile.NewProjectile(player.GetSource_ItemUse(Item), new Vector2(x, player.Center.Y), Vector2.Zero, ModContent.ProjectileType<OrbitalBeam>(),
				player.GetWeaponDamage(Item), 0, player.whoAmI, target?.whoAmI ?? -1);
			Main.NewText("Orbital strike locked on.", new Color(120, 220, 255));
			return true;
		}

		public override void AddRecipes() => CreateRecipe()
			.AddRecipeGroup(RecipeGroupID.IronBar, 6)
			.AddIngredient(ItemID.Lens)
			.AddIngredient(ItemID.FallenStar, 5)
			.AddTile(TileID.Anvils)
			.Register();
	}

	/// <summary>Lock-on laser, then a sky beam that sweeps onto its target (ai[0], an NPC index or -1)
	/// and holds it, scorching the ground where it first landed.</summary>
	public class OrbitalBeam : ModProjectile
	{
		public override string Texture => "SeedArsenal/Assets/HomingMissile"; // unused: drawn procedurally
		const int Lock = 45, Fire = 120, Fade = 20;

		public override void SetDefaults()
		{
			Projectile.width = Projectile.height = 8;
			Projectile.friendly = false; Projectile.tileCollide = false; Projectile.penetrate = -1;
			Projectile.timeLeft = Lock + Fire + Fade;
		}

		int Age => Lock + Fire + Fade - Projectile.timeLeft;
		public bool Firing => Age >= Lock && Age < Lock + Fire;
		float Width => Age < Lock ? 2f : Age < Lock + 10 ? MathHelper.Lerp(8, 110, (Age - Lock) / 10f) : Age < Lock + Fire ? 110 + 10 * MathF.Sin(Age * 0.5f) : 110 * Projectile.timeLeft / (float)Fade;
		float ground0 = -1; // the surface where the beam first landed: it scorches, it doesn't dig forever
		float Ground => ground0 > 0 ? ground0 : Fx.SurfaceTile((int)(Projectile.Center.X / 16)) * 16f;

		public override void AI()
		{
			int id = (int)Projectile.ai[0];
			if (id >= 0 && Main.npc[id].active) // sweep onto the target
				Projectile.position.X += (Main.npc[id].Center.X - Projectile.Center.X) * (Age < Lock ? 0.2f : 0.06f);
			var ground = new Vector2(Projectile.Center.X, Ground);
			if (Age < Lock)
			{
				if (Age % 15 == 0) SoundEngine.PlaySound(SoundID.MenuTick with { Pitch = 0.6f, Volume = 1f });
				return;
			}
			if (Age == Lock)
			{
				ground0 = Fx.SurfaceTile((int)(Projectile.Center.X / 16)) * 16f;
				SoundEngine.PlaySound(SoundID.Zombie104 with { Volume = 1f });
				SoundEngine.PlaySound(SoundID.Item14 with { Pitch = -0.8f });
				Fx.Flash(0.3f);
			}
			if (Age >= Lock + Fire) return;
			float w = Width;
			Main.instance.CameraModifiers.Add(new PunchCameraModifier(ground, Main.rand.NextVector2Unit(), 3.5f, 12f, 4, 3000f, "orbital"));
			for (int i = 0; i < 10; i++)
				Dust.NewDustPerfect(ground + new Vector2(Main.rand.NextFloat(-w / 2, w / 2), -4), i % 3 == 0 ? DustID.Smoke : DustID.Electric,
					new Vector2(Main.rand.NextFloat(-9, 9), -Main.rand.NextFloat(2, 9)), 0, default, 2f).noGravity = true;
			for (int k = 0; k < 8; k++)
				Lighting.AddLight(new Vector2(Projectile.Center.X, ground.Y - k * 120), 0.8f, 1.4f, 2f);
			if (Projectile.owner != Main.myPlayer) return;
			if (Age % 15 == 0) Fx.Blast(ground + new Vector2(0, 16), 2); // scorch a shallow trench
			if (Age % 6 == 0)
			{
				var column = new Rectangle((int)(Projectile.Center.X - w / 2), (int)(Main.screenPosition.Y - 400), (int)w, (int)(ground.Y - Main.screenPosition.Y + 400));
				foreach (var n in Main.ActiveNPCs)
					if (!n.friendly && !n.townNPC && n.Hitbox.Intersects(column)) n.SimpleStrikeNPC(Projectile.damage, 0, Main.rand.NextBool(4), 0f, DamageClass.Magic);
			}
		}

		public override bool PreDraw(ref Color lightColor)
		{
			float x = Projectile.Center.X, top = Main.screenPosition.Y - 200, bottom = Ground;
			var a = new Vector2(x, top); var b = new Vector2(x, bottom);
			Fx.Additive(true);
			if (Age < Lock)
			{
				float blink = (Age / 5) % 2 == 0 ? 1f : 0.4f;
				Fx.Line(a, b, 3, new Color(255, 40, 40) * blink);
				Main.spriteBatch.Draw(Fx.DiscTexture(), b - Main.screenPosition, null, new Color(255, 60, 60) * blink, 0, new Vector2(12), 1.4f, SpriteEffects.None, 0);
			}
			else
			{
				float w = Width;
				Fx.Line(a, b, w * 1.8f, new Color(40, 120, 255) * 0.35f);
				Fx.Line(a, b, w, new Color(120, 220, 255) * 0.75f);
				Fx.Line(a, b, w * 0.45f, Color.White);
				Main.spriteBatch.Draw(Fx.DiscTexture(), b - Main.screenPosition, null, new Color(120, 210, 255) * 0.45f, 0, new Vector2(12), w / 20f, SpriteEffects.None, 0);
			}
			Fx.Additive(false);
			return false;
		}
	}
}
