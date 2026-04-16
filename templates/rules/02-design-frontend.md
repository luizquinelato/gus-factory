# Regras de Design System e Frontend

Estas regras são INEGOCIÁVEIS e devem ser aplicadas em todas as interações e geração de código frontend.

## 1. Cores e Variáveis CSS
- NUNCA use cores hardcoded no Tailwind (ex: `bg-blue-500`, `text-red-600`).
- SEMPRE use as variáveis CSS definidas no Design System (ex: `bg-primary`, `text-on-surface`, `bg-action-delete`).
- O sistema de cores é multi-tenant e dinâmico; usar cores hardcoded quebra a personalização do cliente.

## 2. Roteamento de Abas
- NUNCA use estado local (`useState`) para controlar a navegação entre abas principais de uma página.
- SEMPRE use rotas dedicadas do React Router (ex: `/settings/profile`, `/settings/billing`).
- Isso garante que a URL seja compartilhável e que o botão "Voltar" do navegador funcione corretamente.

## 3. Ícones
- Utilize EXCLUSIVAMENTE a biblioteca Phosphor Icons.
- Aproveite os 6 pesos disponíveis (thin, light, regular, bold, fill, duotone) conforme o contexto visual.

## 4. Componentes Base
- Utilize componentes baseados em Radix UI ou Headless UI para acessibilidade (a11y).
- Encapsule a lógica complexa em componentes reutilizáveis (ex: `PrimaryButton`, `Card`, `Modal`).

## 5. Chamadas de API
- NUNCA use `fetch` ou `axios` diretamente nos componentes.
- SEMPRE use a instância configurada do `apiClient` (que já injeta o token JWT e trata erros 401).
- Utilize React Query (ou SWR) para gerenciar o estado do servidor, cache e revalidação de dados.
