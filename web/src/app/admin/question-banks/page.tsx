
"use client";
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { BookOpenCheckIcon, BookOpenIcon, BookIcon, ExternalLinkIcon } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';

export default function QuestionBanksPage() {
  const { t } = useTranslation();

  type DifficultyItem = {
    nameKey: 'admin.questionBanks.easy.title' | 'admin.questionBanks.hybrid.title' | 'admin.questionBanks.hard.title';
    difficulty: 'easy' | 'hybrid' | 'hard';
    icon: React.ElementType;
    descriptionKey: 'admin.questionBanks.easy.description' | 'admin.questionBanks.hybrid.description' | 'admin.questionBanks.hard.description';
    buttonKey: 'admin.questionBanks.easy.button' | 'admin.questionBanks.hybrid.button' | 'admin.questionBanks.hard.button';
  };

  const difficulties: Array<DifficultyItem> = [
    { nameKey: 'admin.questionBanks.easy.title', difficulty: 'easy', icon: BookOpenCheckIcon, descriptionKey: 'admin.questionBanks.easy.description', buttonKey: 'admin.questionBanks.easy.button' },
    { nameKey: 'admin.questionBanks.hybrid.title', difficulty: 'hybrid', icon: BookOpenIcon, descriptionKey: 'admin.questionBanks.hybrid.description', buttonKey: 'admin.questionBanks.hybrid.button' },
    { nameKey: 'admin.questionBanks.hard.title', difficulty: 'hard', icon: BookIcon, descriptionKey: 'admin.questionBanks.hard.description', buttonKey: 'admin.questionBanks.hard.button' },
  ];

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {difficulties.map((item) => (
        <Card key={item.difficulty}>
          <CardHeader>
            <CardTitle className="flex items-center">
              <item.icon className="mr-2 h-5 w-5 text-primary" />
              {t(item.nameKey)}
            </CardTitle>
            <CardDescription>{t(item.descriptionKey)}</CardDescription>
          </CardHeader>
          <CardContent>
            <Link href={`/admin/question-banks/${item.difficulty}`} passHref>
              <Button variant="outline">
                {t(item.buttonKey)}
                <ExternalLinkIcon className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

    