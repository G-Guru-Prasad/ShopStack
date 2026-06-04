from django.conf import settings
from django.db import migrations, models
import pgvector.django


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        pgvector.django.VectorExtension(),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('source_path', models.CharField(max_length=512, unique=True)),
                ('kind', models.CharField(
                    choices=[
                        ('runbook', 'Runbook'),
                        ('onboarding', 'Onboarding'),
                        ('architecture', 'Architecture'),
                        ('other', 'Other'),
                    ],
                    default='other',
                    max_length=20,
                )),
                ('content_hash', models.CharField(max_length=64)),
                ('indexed_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'doc_agent_documents'},
        ),
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('title', models.CharField(blank=True, default='', max_length=80)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='doc_agent_conversations',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'doc_agent_conversations', 'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='DocumentChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('chunk_index', models.PositiveIntegerField()),
                ('text', models.TextField()),
                ('embedding', pgvector.django.VectorField(dimensions=1024)),
                ('start_line', models.PositiveIntegerField(blank=True, null=True)),
                ('end_line', models.PositiveIntegerField(blank=True, null=True)),
                ('document', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='chunks',
                    to='doc_agent.document',
                )),
            ],
            options={
                'db_table': 'doc_agent_document_chunks',
                'unique_together': {('document', 'chunk_index')},
            },
        ),
        migrations.AddIndex(
            model_name='documentchunk',
            index=pgvector.django.HnswIndex(
                ef_construction=64,
                fields=['embedding'],
                m=16,
                name='doc_chunk_embedding_hnsw',
                opclasses=['vector_cosine_ops'],
            ),
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('role', models.CharField(
                    choices=[('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')],
                    max_length=16,
                )),
                ('content', models.TextField()),
                ('guardrails_verdict', models.JSONField(blank=True, null=True)),
                ('verifier_verdict', models.JSONField(blank=True, null=True)),
                ('not_fully_verified', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cited_chunks', models.ManyToManyField(
                    blank=True,
                    related_name='cited_in_messages',
                    to='doc_agent.documentchunk',
                )),
                ('conversation', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='messages',
                    to='doc_agent.conversation',
                )),
            ],
            options={'db_table': 'doc_agent_messages', 'ordering': ['created_at']},
        ),
    ]
