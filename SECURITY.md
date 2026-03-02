# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in SecondBrain, please report it responsibly:

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email security@secondbrain.local with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any known mitigations

## Security Features

- **Environment-driven configuration**: Sensitive settings via environment variables
- **Input validation**: All user inputs validated before processing
- **Error handling**: Granular error types prevent information leakage
- **Rate limiting**: Ollama API rate limiting prevents abuse
- **Connection validation**: Service health checks with TTL caching

## Security Best Practices

1. Never commit API keys or credentials
2. Use the `.env` file for local configuration
3. Set strong credentials for MongoDB in production
4. Enable TLS for MongoDB connections
5. Keep dependencies updated (`uv pip check`)

## Acknowledgments

We thank the following for their security research:
- [Your Name Here]
