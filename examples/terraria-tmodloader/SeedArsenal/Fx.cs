using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.Graphics.CameraModifiers;
using Terraria.ID;
using Terraria.ModLoader;

namespace SeedArsenal
{
	/// <summary>
	/// Effects shared by the weapons and enemies: pixel-puff explosions, the nuke (crater, fireball,
	/// mushroom cloud), a screen flash and tint, a camera that can be pulled over to a point, and small
	/// drawing helpers. Visuals only run on clients; world edits run where each caller says.
	/// </summary>
	public class Fx : ModSystem
	{
		const int CraterR = 24;       // tiles
		const float CloudH = 340f;    // px above ground zero where the mushroom cap spreads out
		const int NukeFxFrames = 220; // the fireball, stem, cap and glow all happen within this

		static float flash, tint;
		static Vector2 camFocus, camOffset;
		static int focusTime;
		static readonly List<(Vector2 at, int age)> nukes = new();

		public override void OnWorldLoad() => Reset();
		public override void OnWorldUnload() => Reset();

		static void Reset()
		{
			puffs.Clear();
			nukes.Clear();
			flash = tint = 0;
			focusTime = 0;
			camOffset = Vector2.Zero;
		}

		public override void Unload()
		{
			// a GPU resource: dispose it on the main thread
			var d = disc;
			disc = null;
			if (d != null) Main.QueueMainThreadAction(d.Dispose);
		}

		// ------------------------------------------------------------------ helpers

		/// <summary>First solid tile from the sky down in column x.</summary>
		public static int SurfaceTile(int x)
		{
			x = Math.Clamp(x, 0, Main.maxTilesX - 1);
			for (int y = 40; y < Main.maxTilesY - 10; y++)
			{
				var tile = Main.tile[x, y];
				if (tile.HasTile && Main.tileSolid[tile.TileType] && !Main.tileSolidTop[tile.TileType]) return y;
			}
			return (int)Main.worldSurface;
		}

		/// <summary>The nearest enemy that can be targeted, optionally filtered.</summary>
		public static NPC Nearest(Vector2 from, float range, Func<NPC, bool> ok = null)
		{
			NPC best = null; float bd = range;
			foreach (var n in Main.ActiveNPCs)
			{
				if (!n.CanBeChasedBy() || (ok != null && !ok(n))) continue;
				float d = Vector2.Distance(n.Center, from);
				if (d < bd) { bd = d; best = n; }
			}
			return best;
		}

		/// <summary>Restarts the (already begun) sprite batch with additive or normal blending.</summary>
		public static void Additive(bool on)
		{
			Main.spriteBatch.End();
			Main.spriteBatch.Begin(SpriteSortMode.Deferred, on ? BlendState.Additive : BlendState.AlphaBlend, Main.DefaultSamplerState,
				DepthStencilState.None, Main.Rasterizer, null, Main.GameViewMatrix.TransformationMatrix);
		}

		/// <summary>A line segment in world space as a stretched pixel.</summary>
		public static void Line(Vector2 a, Vector2 b, float width, Color c)
		{
			var d = b - a;
			Main.spriteBatch.Draw(TextureAssets.MagicPixel.Value, a - Main.screenPosition, new Rectangle(0, 0, 1, 1), c, d.ToRotation(),
				new Vector2(0, 0.5f), new Vector2(d.Length(), width), SpriteEffects.None, 0f);
		}

		/// <summary>The shared 24x24 pixel disc (puffs, black holes, beam impacts). Main thread / draw only.</summary>
		public static Texture2D DiscTexture()
		{
			if (disc == null)
			{
				// 24x24 disc with a one-pixel darker rim: reads as a pixel-art puff when scaled up
				const int n = 24;
				var data = new Color[n * n];
				for (int y = 0; y < n; y++)
					for (int x = 0; x < n; x++)
					{
						float d = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(n / 2f));
						data[y * n + x] = d < n / 2f - 1.5f ? Color.White : d < n / 2f ? new Color(200, 200, 200) : Color.Transparent;
					}
				disc = new Texture2D(Main.graphics.GraphicsDevice, n, n);
				disc.SetData(data);
			}
			return disc;
		}

		// ------------------------------------------------------------------ explosions

		/// <summary>Clears a disc of tiles (containers survive). Run it on one machine, the projectile
		/// owner's: like vanilla explosives, each broken tile is sent on in multiplayer.</summary>
		public static void Blast(Vector2 at, int radius)
		{
			int cx = (int)(at.X / 16), cy = (int)(at.Y / 16);
			for (int x = cx - radius; x <= cx + radius; x++)
				for (int y = cy - radius; y <= cy + radius; y++)
				{
					if (!WorldGen.InWorld(x, y, 5) || (x - cx) * (x - cx) + (y - cy) * (y - cy) > radius * radius) continue;
					var tile = Main.tile[x, y];
					if (!tile.HasTile || Main.tileContainer[tile.TileType]) continue;
					WorldGen.KillTile(x, y); // drops the blocks, like any mined tile
					if (Main.netMode != NetmodeID.SinglePlayer && !Main.tile[x, y].HasTile)
						NetMessage.SendData(MessageID.TileManipulation, -1, -1, null, 0, x, y);
				}
		}

		/// <summary>Enemy death pop: a few fire/smoke puffs.</summary>
		public static void SmallBoom(Vector2 at, float scale = 1f)
		{
			for (int i = 0; i < 7; i++)
				Emit(at + Main.rand.NextVector2Circular(10, 10), Main.rand.NextVector2Circular(2, 2) + new Vector2(0, -0.6f), Main.rand.NextFloat(8, 16) * scale, Main.rand.Next(40, 70), 0.25f * scale);
		}

		/// <summary>Boss death: a big fireball of pixel puffs, flash, shake.</summary>
		public static void BigBoom(Vector2 c)
		{
			if (Main.dedServ) return;
			SoundEngine.PlaySound(SoundID.Item14 with { Pitch = -0.7f });
			SoundEngine.PlaySound(SoundID.Item62 with { Pitch = -0.5f });
			SoundEngine.PlaySound(SoundID.DD2_ExplosiveTrapExplode with { Pitch = -0.4f });
			Flash(0.25f);
			tint = Math.Max(tint, 0.35f);
			Main.instance.CameraModifiers.Add(new PunchCameraModifier(c, Vector2.UnitY, 16f, 7f, 60, 4000f, "boss"));
			var rnd = Main.rand;
			for (int i = 0; i < 70; i++)
				Emit(c + rnd.NextVector2Circular(90, 40), rnd.NextVector2Circular(7, 5), rnd.NextFloat(26, 60), rnd.Next(70, 140), 0.45f);
			for (int i = 0; i < 80; i++)
				Dust.NewDustPerfect(c + rnd.NextVector2Circular(80, 30), i % 2 == 0 ? DustID.Torch : DustID.Electric, rnd.NextVector2Circular(14, 14), 0, default, 2.4f).noGravity = true;
		}

		/// <summary>White screen flash (0..1), fades over half a second.</summary>
		public static void Flash(float a) => flash = Math.Max(flash, a);

		/// <summary>The tactical nuke at ground level: crater, everything nearby dies, the local player
		/// is thrown back, then the fireball and mushroom cloud play out (NukeFx).</summary>
		public static void Detonate(Vector2 ground)
		{
			// the crater only depends on the world, so every machine digs the same one (no tile sync)
			Crater(ground);
			if (Main.netMode != NetmodeID.MultiplayerClient)
				foreach (var n in Main.ActiveNPCs)
					if (!n.townNPC && Vector2.Distance(n.Center, ground) < CraterR * 16 * 2.2f) n.StrikeInstantKill();
			if (Main.dedServ) return;
			nukes.Add((ground, 0));
			flash = 1f; tint = 1f;
			// layered vanilla sounds, pitched down, heard at full volume wherever the player is
			SoundEngine.PlaySound(SoundID.Item14 with { Volume = 1f, Pitch = -0.9f });
			SoundEngine.PlaySound(SoundID.Item62 with { Volume = 1f, Pitch = -0.6f });
			SoundEngine.PlaySound(SoundID.DD2_ExplosiveTrapExplode with { Volume = 1f, Pitch = -0.7f });
			SoundEngine.PlaySound(SoundID.DD2_BetsyFireballImpact with { Volume = 1f, Pitch = -0.8f });
			SoundEngine.PlaySound(SoundID.Roar with { Volume = 0.8f, Pitch = -1f });
			Main.instance.CameraModifiers.Add(new PunchCameraModifier(ground, Vector2.UnitY, 26f, 7f, 110, 6000f, "nuke"));
			var p = Main.LocalPlayer;
			if (Math.Abs(p.Center.X - ground.X) < 80 * 16)
			{
				p.velocity = new Vector2(Math.Sign(p.Center.X - ground.X) * 7f, -6f);
				p.immune = true; p.immuneTime = 120;
			}
		}

		static void Crater(Vector2 ground)
		{
			int cx = (int)(ground.X / 16), cy = (int)(ground.Y / 16) + 6;
			int R = CraterR, rim = R + 3, vapor = (int)(R * 2.2f);
			for (int x = cx - vapor; x <= cx + vapor; x++)
				for (int y = cy - vapor; y <= cy + rim; y++)
				{
					if (!WorldGen.InWorld(x, y, 5)) continue;
					var tile = Main.tile[x, y];
					int d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy);
					if (d2 <= R * R) { tile.ClearEverything(); continue; } // vaporised
					if (!tile.HasTile) continue;
					if (!Main.tileSolid[tile.TileType]) { tile.ClearTile(); continue; } // trees, grass, flowers in the blast radius
					if (d2 <= rim * rim) tile.TileType = TileID.Ash; // scorched rim
				}
			WorldGen.RangeFrame(cx - vapor - 2, cy - vapor - 2, cx + vapor + 2, cy + rim + 2);
			for (int x = cx - vapor - 2; x <= cx + vapor + 2; x++)
				for (int y = cy - vapor - 2; y <= cy + rim + 2; y++)
					if (WorldGen.InWorld(x, y, 5)) WorldGen.SquareWallFrame(x, y);
		}

		/// <summary>Frame f of a nuke's fireball, ground shock ring, rising stem and mushroom cap.</summary>
		static void NukeFx(Vector2 c, int f)
		{
			var rnd = Main.rand;
			if (f == 0) // fireball
				for (int i = 0; i < 60; i++)
					Emit(c + rnd.NextVector2Circular(40, 30), rnd.NextVector2Circular(6, 4) + new Vector2(0, -2), rnd.NextFloat(40, 90), rnd.Next(90, 150), 0.6f);
			if (f < 40) // ground shock ring
				for (int i = 0; i < 4; i++)
				{
					float s = rnd.NextBool() ? 1 : -1;
					Emit(c + new Vector2(s * rnd.NextFloat(20, 60), -rnd.NextFloat(0, 20)), new Vector2(s * rnd.NextFloat(10, 18), -rnd.NextFloat(0, 1.5f)), rnd.NextFloat(18, 30), rnd.Next(60, 110), 0.25f);
				}
			if (f < 110) // stem: rises and rolls into the cap
				for (int i = 0; i < 3; i++)
					Emit(c + new Vector2(rnd.NextFloat(-35, 35), -rnd.NextFloat(0, 30)), new Vector2(rnd.NextFloat(-0.3f, 0.3f), -rnd.NextFloat(8, 11)), rnd.NextFloat(26, 40), rnd.Next(170, 250), 0.14f, stem: true, origin: c);
			if (f > 12 && f < 130) // cap
				for (int i = 0; i < 3; i++)
				{
					float s = rnd.NextBool() ? 1 : -1;
					Emit(c + new Vector2(s * rnd.NextFloat(0, 60 + f * 1.6f), -CloudH + rnd.NextFloat(-40, 40)), new Vector2(s * rnd.NextFloat(0.8f, 2.8f), rnd.NextFloat(-0.8f, 0.3f)), rnd.NextFloat(40, 70), rnd.Next(160, 240), 0.16f, true);
				}
			if (f < 60)
				for (int i = 0; i < 20; i++)
					Dust.NewDustPerfect(c + rnd.NextVector2Circular(90, 50), DustID.Torch, rnd.NextVector2Circular(9, 9), 0, default, 2.5f).noGravity = true;
			if (f < NukeFxFrames)
				for (int k = 0; k < 5; k++)
					Lighting.AddLight(c + new Vector2(0, -k * 100), 2f * (1 - f / (float)NukeFxFrames), 1.2f * (1 - f / (float)NukeFxFrames), 0.4f);
		}

		// ------------------------------------------------------------------ pixel puffs

		/// <summary>One blob of fireball / smoke. Drawn as a chunky pixel disc (point-sampled) so it
		/// fits Terraria's look; colour runs white-hot -> orange -> red -> grey smoke as it ages.</summary>
		struct Puff { public Vector2 Pos, Vel, Origin; public float R, Grow; public int Age, Life; public bool Cap, Stem; }
		static readonly List<Puff> puffs = new();
		static Texture2D disc;

		static void Emit(Vector2 pos, Vector2 vel, float r, int life, float grow = 0.3f, bool cap = false, bool stem = false, Vector2 origin = default)
		{
			if (Main.dedServ) return;
			puffs.Add(new Puff { Pos = pos, Vel = vel, R = r, Grow = grow, Life = life, Cap = cap, Stem = stem, Origin = origin });
		}

		static void UpdatePuffs()
		{
			for (int i = puffs.Count - 1; i >= 0; i--)
			{
				var q = puffs[i];
				q.Age++;
				if (q.Age >= q.Life) { puffs.RemoveAt(i); continue; }
				q.Pos += q.Vel;
				q.R += q.Grow;
				if (q.Stem && q.Pos.Y < q.Origin.Y - CloudH) // stem puffs hit the ceiling: stop rising, curl outwards
				{
					q.Vel.Y *= 0.8f;
					q.Vel.X += Math.Sign(q.Pos.X - q.Origin.X + 0.01f) * 0.25f;
				}
				q.Vel *= q.Cap ? 0.985f : 0.975f;
				q.Vel.Y -= q.Cap ? 0.005f : q.Stem ? 0.03f : 0.01f; // hot air keeps rising
				puffs[i] = q;
			}
		}

		static Color PuffColor(float a)
		{
			var hot = new Color(255, 250, 225); var fire = new Color(255, 160, 50); var ember = new Color(185, 70, 35); var smoke = new Color(95, 85, 80);
			if (a < 0.06f) return Color.Lerp(hot, fire, a / 0.06f);
			if (a < 0.22f) return Color.Lerp(fire, ember, (a - 0.06f) / 0.16f);
			if (a < 0.45f) return Color.Lerp(ember, smoke, (a - 0.22f) / 0.23f);
			return smoke;
		}

		// ------------------------------------------------------------------ camera

		/// <summary>Pulls the camera over to a point for a while (the nuke's ground zero), then eases back.</summary>
		public static void Focus(Vector2 at, int frames)
		{
			camFocus = at;
			focusTime = Math.Max(focusTime, frames);
		}

		// ------------------------------------------------------------------ hooks

		public override void PostUpdateEverything()
		{
			if (Main.dedServ) return;
			for (int i = nukes.Count - 1; i >= 0; i--)
			{
				var (at, age) = nukes[i];
				NukeFx(at, age);
				if (age >= NukeFxFrames) nukes.RemoveAt(i);
				else nukes[i] = (at, age + 1);
			}
			flash = Math.Max(0, flash - 1f / 30);
			tint = Math.Max(0, tint - 1f / 150);
			if (focusTime > 0) focusTime--;
		}

		public override void PostUpdateDusts() { if (puffs.Count > 0) UpdatePuffs(); }

		public override void PostDrawTiles()
		{
			if (puffs.Count == 0) return;
			var tex = DiscTexture();
			var sb = Main.spriteBatch;
			sb.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.PointClamp, DepthStencilState.None, RasterizerState.CullNone, null, Main.GameViewMatrix.TransformationMatrix);
			// oldest (smoke) first, fresh fire on top
			for (int i = 0; i < puffs.Count; i++)
			{
				var q = puffs[i];
				float a = q.Age / (float)q.Life;
				float alpha = a > 0.75f ? 1 - (a - 0.75f) / 0.25f : 1f;
				sb.Draw(tex, q.Pos - Main.screenPosition, null, PuffColor(a) * alpha, 0f, new Vector2(12), q.R / 12f, SpriteEffects.None, 0f);
			}
			sb.End();
		}

		public override void ModifyScreenPosition()
		{
			// an offset from the normal player-centred view: screen shake is applied before this hook,
			// so setting the position outright would cancel it
			var want = focusTime > 0 ? camFocus - Main.LocalPlayer.Center : Vector2.Zero;
			camOffset = Vector2.Lerp(camOffset, want, 0.05f);
			if (focusTime == 0 && camOffset.LengthSquared() < 1f) camOffset = Vector2.Zero;
			Main.screenPosition += camOffset;
		}

		public override void PostDrawInterface(SpriteBatch sb)
		{
			if (flash <= 0 && tint <= 0) return;
			var px = TextureAssets.MagicPixel.Value;
			// this layer is drawn with the UI scale applied: divide it out to cover the whole screen
			var screen = new Rectangle(0, 0, (int)(Main.screenWidth / Main.UIScale) + 1, (int)(Main.screenHeight / Main.UIScale) + 1);
			if (tint > 0) sb.Draw(px, screen, new Color(255, 120, 30) * (0.15f * tint));
			if (flash > 0) sb.Draw(px, screen, Color.White * flash);
		}
	}
}
