#!/usr/bin/env python3
"""
Content Creator Agent - Generates hooks and captions for Instagram Reels
Supports multiple personas: TikTok Strategist, Growth Hacker, Content Creator
"""

import os
import json
import time
import random
import schedule
from datetime import datetime
from typing import Dict, List, Optional
import redis
from openai import OpenAI
import anthropic
from dotenv import load_dotenv

load_dotenv()

class ContentCreator:
    def __init__(self):
        self.redis_client = redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
            decode_responses=True
        )
        self.persona = os.getenv('CREATOR_PERSONA', 'tiktok_strategist')
        self.queue_name = os.getenv('QUEUE_NAME', 'pending_hooks')
        
        # Language setting must be before load_persona!
        self.language = os.getenv('CONTENT_LANGUAGE', 'en')

        # Initialize AI clients
        self.openai = OpenAI() if os.getenv('OPENAI_API_KEY') else None
        self.anthropic = anthropic.Anthropic() if os.getenv('ANTHROPIC_API_KEY') else None

        self.load_persona()

    def load_persona(self):
        """Load the selected persona configuration"""
        personas_en = {
            'tiktok_strategist': {
                'name': 'TikTok Strategist',
                'style': 'viral, fast-paced, trend-savvy',
                'hook_patterns': [
                    'POV: {situation}',
                    'Nobody told me {revelation}',
                    'The {thing} they don\'t want you to see',
                    'Wait for it... {payoff}',
                    '{number} reasons why {outcome}',
                    'This {thing} changed everything',
                    'I tried {thing} so you don\'t have to',
                ],
                'tone': 'energetic, relatable, slightly chaotic',
                'max_chars': 150
            },
            'growth_hacker': {
                'name': 'Growth Hacker',
                'style': 'data-driven, psychological triggers, viral mechanics',
                'hook_patterns': [
                    'The {thing} that made me ${amount}',
                    'Stop doing {thing} if you want to {goal}',
                    'This one {thing} = {result}',
                    '{Number}% of people don\'t know this about {topic}',
                    'Steal this {thing} (thank me later)',
                    'Why your {thing} isn\'t working',
                    'The {topic} loophole',
                ],
                'tone': 'direct, urgent, value-first',
                'max_chars': 125
            },
            'content_creator': {
                'name': 'Content Creator',
                'style': 'storytelling, brand-consistent, engaging',
                'hook_patterns': [
                    'Let me tell you about {thing}',
                    'The day I discovered {revelation}',
                    'Why I stopped {thing}',
                    'This is what {number} days of {thing} looks like',
                    'The {thing} I wish I knew sooner',
                    'Real talk: {honest_opinion}',
                    'Behind the scenes of {thing}',
                ],
                'tone': 'authentic, conversational, trustworthy',
                'max_chars': 200
            }
        }

        personas_es = {
            'tiktok_strategist': {
                'name': 'Estratega de TikTok',
                'style': 'viral, rápido, al día con tendencias',
                'hook_patterns': [
                    'POV: {situation}',
                    'Nadie me dijo que {revelation}',
                    'Lo que no quieren que sepas sobre {thing}',
                    'Espera el final... {payoff}',
                    '{number} razones por las que {outcome}',
                    'Esto cambió todo',
                    'Probé {thing} para que tú no tengas que hacerlo',
                ],
                'tone': 'energético, cercano, un poco caótico',
                'max_chars': 150
            },
            'growth_hacker': {
                'name': 'Growth Hacker',
                'style': 'basado en datos, gatillos psicológicos, mecánicas virales',
                'hook_patterns': [
                    'Lo que me hizo ganar ${amount}',
                    'Deja de {thing} si quieres {goal}',
                    'Esto {thing} = {result}',
                    'El {Number}% de la gente no sabe esto sobre {topic}',
                    'Copia esto (luego me agradeces)',
                    'Por qué tu {thing} no funciona',
                    'El truco de {topic}',
                ],
                'tone': 'directo, urgente, valor primero',
                'max_chars': 125
            },
            'content_creator': {
                'name': 'Creador de Contenido',
                'style': 'narrativa, consistente con la marca, atractivo',
                'hook_patterns': [
                    'Déjame contarte sobre {thing}',
                    'El día que descubrí {revelation}',
                    'Por qué dejé de {thing}',
                    'Así se ven {number} días de {thing}',
                    'Lo que desearía haber sabido antes',
                    'Hablemos claro: {honest_opinion}',
                    'Detrás de cámaras de {thing}',
                ],
                'tone': 'auténtico, conversacional, confiable',
                'max_chars': 200
            }
        }

        personas = personas_es if getattr(self, 'language', 'en') == 'es' else personas_en

        self.config = personas.get(self.persona, personas['tiktok_strategist'])
        print(f"Loaded persona: {self.config['name']}")

    def generate_hook(self, topic: Optional[str] = None) -> Dict:
        """Generate a hook using the current persona"""
        if not topic:
            topics = [
                'cannabis', 'dispensary', 'wellness', 'self-care',
                'small business', 'local business', 'customer service',
                'product discovery', 'community', 'education'
            ]
            topic = random.choice(topics)

        # Try AI generation first
        hook = self.generate_with_ai(topic)

        # Fallback to template if AI fails
        if not hook:
            hook = self.generate_from_template(topic)

        caption = self.generate_caption(topic, hook)
        hashtags = self.generate_hashtags(topic)

        return {
            'id': f"hook_{int(time.time())}_{random.randint(1000, 9999)}",
            'persona': self.config['name'],
            'topic': topic,
            'hook': hook,
            'caption': caption,
            'hashtags': hashtags,
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }

    def generate_with_ai(self, topic: str) -> Optional[str]:
        """Generate hook using AI"""
        prompt = f"""You are a {self.config['name']} specializing in viral Instagram Reels.

Your style: {self.config['style']}
Your tone: {self.config['tone']}
Max characters: {self.config['max_chars']}

Create a HOOK (first 3 seconds text) for a Reel about: {topic}

Rules:
- MUST grab attention instantly
- Use pattern interrupt or curiosity gap
- Keep it under {self.config['max_chars']} characters
- No emojis in the hook text
- Write only the hook, nothing else

Examples of your style:
{chr(10).join(random.sample(self.config['hook_patterns'], 3))}

Your hook:"""

        try:
            if self.anthropic:
                response = self.anthropic.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=100,
                    temperature=0.9,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text.strip()
            elif self.openai:
                response = self.openai.chat.completions.create(
                    model="gpt-4",
                    max_tokens=100,
                    temperature=0.9,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"AI generation failed: {e}")

        return None

    def generate_from_template(self, topic: str) -> str:
        """Generate hook from template patterns"""
        template = random.choice(self.config['hook_patterns'])

        # Fill in template variables
        replacements = {
            '{situation}': f'you found the best {topic}',
            '{revelation}': f'{topic} actually works',
            '{thing}': topic,
            '{payoff}': 'the reveal at the end',
            '{number}': str(random.randint(3, 10)),
            '{outcome}': f'you\'ll love {topic}',
            '{amount}': str(random.randint(1, 50)) + 'k',
            '{goal}': 'succeed',
            '{topic}': topic,
            '{Number}': str(random.randint(70, 99)),
            '{result}': 'game changer',
            '{honest_opinion}': f'{topic} changed my life'
        }

        hook = template
        for key, value in replacements.items():
            hook = hook.replace(key, value)

        return hook

    def generate_caption(self, topic: str, hook: str) -> str:
        """Generate full caption with CTA"""
        if self.language == 'es':
            ctas = [
                "Guarda esto para después",
                "Etiqueta a alguien que necesita ver esto",
                "Comenta qué piensas",
                "Comparte con tus amigos",
                "Comenta si estás de acuerdo",
                "Síguenos para más",
                "¿Qué opinas? Cuéntanos",
                "Doble tap si te gustó",
                "Guarda esto",
                "Comparte en stories"
            ]
        else:
            ctas = [
                "Save this for later",
                "Tag someone who needs to see this",
                "Comment your thoughts below",
                "Share this with your friends",
                "Drop a if you agree",
                "Follow for more",
                "What do you think? Tell us below"
            ]

        body = f"{hook}\n\n"
        body += f"{random.choice(ctas)}\n\n"

        return body

    def generate_hashtags(self, topic: str) -> List[str]:
        """Generate relevant hashtags"""
        if self.language == 'es':
            base_tags = ['reels', 'viral', 'tendencia', 'parati']
            extras = ['comunidad', 'descubre', 'pruebaesto', 'fyp', 'viral2024']
        else:
            base_tags = ['reels', 'viral', 'trending', 'explore']
            extras = ['community', 'local', 'discover', 'musttry', 'fyp']

        topic_tags = [topic.replace(' ', ''), topic.replace(' ', '_')]

        return base_tags + topic_tags + random.sample(extras, 3)

    def push_to_queue(self, content: Dict):
        """Push generated content to Redis queue"""
        try:
            self.redis_client.lpush(self.queue_name, json.dumps(content))
            print(f"✓ Pushed hook #{content['id']} to queue")
            self.log_activity(f"Generated hook: {content['hook'][:50]}...")
        except Exception as e:
            print(f"Failed to push to queue: {e}")

    def log_activity(self, message: str):
        """Log activity to file safely"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_dir = '/app/logs'
            # Crear el directorio si no existe
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            log_path = os.path.join(log_dir, 'creator.log')
            with open(log_path, 'a') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"Logging failed: {e}")

    def run_scheduled_generation(self):
        """Generate content on schedule"""
        print(f"Running scheduled generation with {self.config['name']}...")
        content = self.generate_hook()
        self.push_to_queue(content)

    def run(self):
        """Main loop"""
        interval = int(os.getenv('GENERATE_INTERVAL', 3600))  # Default 1 hour

        print(f"Content Creator Agent started")
        print(f"Persona: {self.config['name']}")
        print(f"Schedule: Every {interval} seconds")

        # Generate immediately on startup
        self.run_scheduled_generation()

        # Schedule regular generation
        schedule.every(interval).seconds.do(self.run_scheduled_generation)

        while True:
            schedule.run_pending()
            time.sleep(1)

if __name__ == '__main__':
    creator = ContentCreator()
    creator.run()

